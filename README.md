# python_microservices
This python project demonstrates asynchronous non-blocking micro-services using the Tornado framework.

#### Launch:

```$ python main.py``` 

#### Test Endpoints

##### 1.```curl -v  http://localhost:8000/umbrella?d=http://www.google.com ```
##### 2.```curl -v -H "Content-Type: application/json" -XPOST -d "[ "http://www.fireeye.com/", "https://www.google.com/", "https://www.yahoo.com/", "https://www.microsoft.com/", "http://xkcd.com/", "http://waitbutwhy.com/", "http://cnn.com/", "http://amazon.com/", "http://reddit.com/" ]" http://localhost:8000/submit ```
##### 3.```curl -v  http://localhost:8000/similar?d=http://www.google.com ```