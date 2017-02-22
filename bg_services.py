# -*- coding: utf-8 -*-
# The MIT License (MIT)
# Author - Stephen Goveia 2017
# Email - stephengoveia@gmail.com
##############################
#
#    imports
#
##############################
import logging
import tornado.escape
import tornado.ioloop
import tornado.web
import os.path
import zipfile
import urllib
import csv
import os
import codecs
import json
import redis
import urllib2
import mechanize
import numpy as np
import editdistance
from threading import Thread
from bs4 import BeautifulSoup
from multiprocessing.pool import ThreadPool
#################################################################
# Logging Config
logging.basicConfig(
    level=logging.DEBUG, format='%(asctime)-5s - %(levelname)s - %(message)s')
logger = logging.getLogger('go.goveia.log')
################################################################
'''
__________________________________________________

    BackgroundServices Class

        Delivering asynchronous multi-thread
        task workers and encapsulated Redis client

___________________________________________________
'''


class BackgroundServices(object):
    def __init__(self):
        self.orgUrls = {}
        self.ciscoDB = {}
        self.workerBeez = ThreadPool(10)

        # RedisLabs.com Connect
        redisConn = redis.StrictRedis(
            host='redis-15865.c10.us-east-1-3.ec2.cloud.redislabs.com',
            port=15865,
            password='nanorun789')
        self.redisDB = redisConn

    def background_runner(self, func, callback, args=(), kwds={}):
        # Main async background handler
        def _callback(result):
            tornado.ioloop.IOLoop.instance().add_callback(
                lambda: callback(result))
        self.workerBeez.apply_async(func, args, kwds, _callback)

    def is_redis_available(self):
        # Check for RedisLabs.com connection
            try:
                self.redisDB.get(None)
            except (redis.exceptions.ConnectionError,
                    redis.exceptions.BusyLoadingError):
                    logger.error("No connection to Redis")
                    return False
            logger.info("Redis is Connected")
            return True

    def update_umbrella_thread(self):
        # Lanuches method "update_umbrella" in new thread.
        # Called on server start
        try:
            t = Thread(target=self.update_umbrella)
            t.start()
        except:
            logger.error("Error: Unable to start Umbrella Update")

    def update_umbrella(self):
        # Download, unzip, parse, and insert into
        # dict self.ciscoDB, on server start.
        # Planned future implemention will run an event
        # scheduler every 24 hours, to get the most up-to-date
        # top-1m list.
        logger.info('Updateing Umbrella Cisco List')
        filename, headers = urllib.urlretrieve(
            'http://s3-us-west-1.amazonaws.com/umbrella-static/top-1m.csv.zip')
        try:
            with zipfile.ZipFile(filename) as zf:
                csvfiles = [name for name in zf.namelist()
                            if name.endswith('.csv')]
                for item in csvfiles:
                    with zf.open(item) as source:
                        reader = csv.DictReader(codecs.getreader(
                            'iso-8859-1')(source))
                        for line in reader:
                            data = json.loads(json.dumps(line))
                            # logger.info("{0}".format(data))
                            url = data['google.com']
                            rank = data['1']
                            self.ciscoDB[url] = rank
        except:
            logger.error("Error: Unable Update Umbrella List")

        finally:
            logger.info('Umbrella Cisco List Complete')
            os.unlink(filename)

    def umbrella_search(self, data):
        # Clean data
        url = data['d'][0]
        pure_dom = url.split("//")[-1].split("/")[0]

        # Query for URL from top-1m
        try:
            rank = self.ciscoDB.get(pure_dom, None)
            if rank is not None:
                return "200 %s\n" % json.dumps(dict(rank=rank))
            else:
                return "404: Domain not found in list\n"
        except:
            return "Wow something went wrong getting the url from ciscoDB\n"

    def submit_urls(self, urls):
        if self.is_redis_available() is True:
            try:
                # Clean data
                l = urls.split(',')
                clean_urls = [url.split("//")[-1].split("/")[0] for url in l]

                # Save full urls for later
                self.store_org_urls(l, clean_urls)
                # Set default object
                default_counts = {'a': 0,
                                  'img': 0,
                                  'div': 0,
                                  'avg': 0}

                # Local working collection
                check_status = {}

                # Check if url is already in Redis,
                # if not then set object with default values
                for index in range(len(clean_urls)):
                    if self.redisDB.exists(clean_urls[index]) is not "True":
                        status = self.redisDB.hmset(
                            clean_urls[index], default_counts)
                        check_status[clean_urls[index]] = status

                # Local working collection to hold pass/failed
                # submissions to Redis
                naughty_list = []

                # Append pass/fail list or set status to OK
                for key, val in check_status.items():
                    if val is 'False':
                        naughty_list.append(key)
                        status = "NOT OK"
                    else:
                        status = "OK"
                if status is "OK":
                    return '{0}\n'.format(status)
                else:
                    return 'FAILED to SET: {0}'.format(', '.join(naughty_list))
            except:
                return "FAILED URL INSERT\n"
        else:
            return "No connection to Redis\n"

    def update_counts(self):
        # Check if the url has previously been submitted. If
        # the counts are still the defaults, spin up a thread to get
        # the counts for tags a, img, and div, else just skip that key.
        for key in self.redisDB.scan_iter():
            if self.redisDB.hget(key, 'a') is '0':
                try:
                    t = Thread(target=self.get_counts, args=(key,))
                    t.start()
                except:
                    logger.error("Error: unable to start get_counts thread")
        return "Tag Counts Updating\n"

    def get_counts(self, key):
        # Download key(url) content, search for and count
        # tags <a>,<img>, and <div>, calculate average to create
        # a data point to use for comparison.
        url = self.orgUrls.get(key)
        # logger.info(url)
        attempts = 0
        # Try 3 times to connect to url if error
        while attempts < 3:
            try:
                # Try to connect(tried both urllib2 and mechanize,
                # both produced the same output. Could not download some
                # sites. If they failed to down load I didn't push them to
                # Redis)
                response = urllib2.urlopen(url, timeout=5)
                # response = mechanize.urlopen(url)
                content = response.read()
                soup = BeautifulSoup(content)

                # Find all associated tags in content html
                a = soup.find_all("a")
                img = soup.find_all("img")
                div = soup.find_all("div")
                # logger.info(len(a))

                # Calc average for later comparison
                avg = (len(a)+len(img)+len(div))/3
                updated_counts = {'a': len(a),
                                  'img': len(img),
                                  'div': len(div),
                                  'avg': avg}

                # Push data to Redis
                if self.is_redis_available() is True:
                    try:
                        status = self.redisDB.hmset(key, updated_counts)
                        # logger.info('{0}: {1}'.format(key, updated_counts))
                        # If we failed to connect/download to/from url,
                        # our counts will still be the default 0. So we
                        # remove the KVP from Redis.
                        for keys in self.redisDB.scan_iter():
                            if self.redisDB.hget(keys, 'a') is '0':
                                self.redisDB.delete(keys)
                        if status is "OK":
                            return '{0}\n'.format(status)
                        else:
                            return 'FAILED to SET: {0}'.format(key)
                    except:
                        return "FAILED URL INSERT\n"
                else:
                    return "No connection to Redis\n"
                break
            except urllib2.URLError as e:
                attempts += 1
                # logger.error(type(e))
                logger.error("FAILED DOWNLOAD from: {0}".format(url))

    def find_similar(self, data):
        # Clean data
        url = data['d'][0]
        dom = url.split("//")[-1].split("/")[0]

        # Check if query is in Redis. If not
        # return to Handler
        if self.redisDB.exists(dom) is 'False':
            return "404 Error"
        else:
            # Local working collections
            domsDic = {}
            avglist = []

            # Get average for sent url query
            dom_avg = self.redisDB.hget(dom, 'avg')
            # logger.info(dom_avg)

            # Get averages for all keys in Redis
            for keys in self.redisDB.scan_iter():
                val = self.redisDB.hget(keys, 'avg')
                avglist.append(val)
                domsDic[keys] = val
            # logger.info(avglist)

            # Removes submitted dom and convert list of strings to ints
            avglist.remove(dom_avg)
            sl = map(int, avglist)
            # Find the nearest neighbors average in relation to the
            # query's average i.e. closests average
            most_similar = min(sl, key=lambda x: abs(x-int(dom_avg)))
            # logger.info(most_similar)
            # Get url of selected neighbor
            for key, val in domsDic.items():
                # logger.info("{0}:{1}".format(key, val))
                if int(val) == most_similar:
                    ms_url = key
                    break

            # Get objects from Redis
            query = self.redisDB.hgetall(dom)
            most = self.redisDB.hgetall(ms_url)

            # Build Response. The "score" is calculated
            # using the Levenshtein algorithm, comparing the
            # difference or "distance" of seperation between the
            # the url strings. The more differnt the urls, the higher
            # the result, this addes another level of similarity based on
            # the actual domain string.
            response = {
                        "query": {
                            "url": dom,
                            "counts": {
                                "a": query['a'],
                                "img": query['img'],
                                "div": query['div'],
                            }
                        },
                        "most_similar": {
                            "url": ms_url,
                            "counts": {
                                "a": most['a'],
                                "img": most['img'],
                                "div": most['div'],
                            }
                        },
                        "score": editdistance.eval(dom, ms_url)
                }

            return json.dumps(response)

    def store_org_urls(self, full, trimmed):
        for index in range(len(full)):
            self.orgUrls[trimmed[index]] = full[index].strip('"[,] ')
