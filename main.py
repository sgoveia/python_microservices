# -*- coding: utf-8 -*-
# The MIT License (MIT)
# Author - Stephen Goveia 2017
# Email - stephengoveia@gmail.com
##############################
#
#    imports
#
##############################
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import json
import tornado.escape
from tornado.options import define, options
from tornado.web import asynchronous
from bg_services import logger
from bg_services import BackgroundServices
######################################################
# Tornando Config
define("port", default=8000, help="Its Ok ", type=int)
#######################################################
'''
_________________________________________________________

    Tornando Webserver Application
        Delivering asynchronous multi-threaded
        restful webservice handlers, for data manipulation.


_________________________________________________________
'''


class Application(tornado.web.Application):
    """
    Base class for Tornando application server

    Handlers:
    GET: /umbrella?d=(url)
    POST: /submit
    GET: /similar?d=(url)

    """
    def __init__(self):
        handlers = [
            (r"/umbrella(.*)", UmbrellaHandler),
            (r"/submit", SubmitHandler),
            (r"/similar(.*)", SimilarHandler)]
        tornado.web.Application.__init__(self, handlers, debug=True)


class UmbrellaHandler(tornado.web.RequestHandler):
    """
    Description:
    Endpoint handler for "/umbrella?d=(url)"

    Breif:
    Accepts a GET request to search Cisco's top 1 million domains list for the
    submitted url and return its ranking.

    Response:
    200 {“rank”: <rank> } on successfully finding the url in the list.
    404 If not found

    """
    @asynchronous
    def get(self, input):
        data = json.loads(json.dumps(self.request.arguments))
        g_bg_service.background_runner(
            g_bg_service.umbrella_search, self.on_done, (data,))

    def on_done(self, result):
        self.write("{0}\n".format(result))
        self.finish()

    def write_error(self, status_code, **kwargs):
        self.write("%d error sorry...\n" % status_code)


class SubmitHandler(tornado.web.RequestHandler):
    """
    Description:
    Endpoint handler for "/submit"

    Breif:
    Accepts a POST request containing an array of URLs, to be trimmed to its
    pure domain, and set in the Redis store. The service then for each
    submission lanuches a new thread to download the URL's content. It then
    searches for and counts the html tags <a>,<img>, and <div>. In addition
    it calculates the average of the counts to create a data point to use
    for comparison in the /similar endpoint service.

    Response:
    "ok" on successful submission

    On failure to submit, the service returns:
    FAILED to SET: <domain>,<domain>,...

    """
    @asynchronous
    def post(self):
        data = tornado.escape.json_encode(self.request.body)
        g_bg_service.background_runner(
            g_bg_service.submit_urls, self.after_insert, (data,))

    @asynchronous
    def after_insert(self, result):
        self.write(result)
        g_bg_service.background_runner(
            g_bg_service.update_counts, self.on_done)

    def on_done(self, result):
        self.write(result)
        self.finish()

    def write_error(self, status_code, **kwargs):
        self.write("%d error sorry...\n" % status_code)


class SimilarHandler(tornado.web.RequestHandler):
    """
    Description:
    Endpoint handler for "/similar?d=(url)"

    Breif:
    Accepts a GET request to search a Redis store for the most
    similar url based on the counts object average. The "score" property is
    a value calculated using the Levenshtein algorithm, comparing the
    difference or "distance" of seperation between the
    the url strings. The more differnt the urls, the higher
    the result, this addes another level of similarity based on
    the actual domain string.

    Response:
    {
          "query”: {“
            url”: < requested url > ,
            “counts”: {“
              a”: < count > ,
              “img”: < count > ,
              “div”: < count >
            }
          },
          “most_similar”: {“
            url”: < most similar url > ,
            “counts”: {“
              a”: < count > ,
              “img”: < count > ,
              “div”: < count >
            }
          },
          “score”: < score >
        }
    }

    """
    @asynchronous
    def get(self, input):
        data = json.loads(json.dumps(self.request.arguments))
        g_bg_service.background_runner(
            g_bg_service.find_similar, self.on_done, (data,))

    def on_done(self, result):
        self.write("{0}\n".format(result))
        self.finish()

    def write_error(self, status_code, **kwargs):
        self.write("%d error sorry...\n" % status_code)


if __name__ == "__main__":
    g_bg_service = BackgroundServices()
    g_bg_service.update_umbrella_thread()
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()
