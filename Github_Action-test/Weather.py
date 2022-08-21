# coding=utf-8
import requests
import datetime

import time
import hmac
import hashlib
import base64
import urllib.parse

class MonitorWeather():
    def __init__(self):
        self.result = ""

    def printText(self, daily, date,minCode,maxCode, extraWord, suggestion):
        code_day = int(json["results"][0]["daily"][daily]["code_day"])
        code_night = int(json["results"][0]["daily"][daily]["code_night"])

        # if keyWord in json["results"][0]["daily"][daily]["text_day"] or keyWord in json["results"][0]["daily"][daily]["text_night"]:
        if minCode <= code_day <= maxCode or minCode <= code_night <= maxCode:
            dayText = date + "白天-" + json["results"][0]["daily"][daily]["text_day"]
            nightText = ", " + date + "夜间-" + json["results"][0]["daily"][daily]["text_night"]
            wendu = "，温度：" + json["results"][0]["daily"][daily]["low"] + " ~ " + json["results"][0]["daily"][daily]["high"]
            shui = " 降水概率: " + json["results"][0]["daily"][daily]["precip"]
            shuiliang = " 降水量: " + json["results"][0]["daily"][daily]["rainfall"]
            fengdengji = " 风力等级: " + json["results"][0]["daily"][daily]["wind_scale"]
            result =  dayText + nightText + " ," +extraWord +wendu + fengdengji + suggestion
            # print(result)
            self.result = self.result +result + '\n'


    def Url(self):
        timestamp = str(round(time.time() * 1000))
        secret = 'SECf2b70ca8b507e2ae1e7cf476f3e75fadb8ee869ab34bed495eb361d5155c0865'
        secret_enc = secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        print(timestamp)
        print(sign)
        self.dingdingurl = "https://oapi.dingtalk.com/robot/send?access_token=cad451762de13cc3c67275fe9e939ea3f58cca657a3cac94faedb220952df0a7" + "&timestamp=" + timestamp + "&sign=" + sign;

    def send(self):
        # curTime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        curTime = (datetime.datetime.now() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
        print(curTime)
        data = {
            "msgtype": "text",
            # "text": {"content": curTime +" 上证指数："+self.text},
            "text": {"content": curTime + '    上海' +'\n' +self.result},
            "at": {
                # "atMobiles": [
                #     "156xxxx8827",
                #     "189xxxx8325"
                # ],
                "isAtAll": 'true'
            }
        }
        r = requests.post(self.dingdingurl, json=data)
        print(r)

# https://www.seniverse.com/products?iid=6729056a-d639-486e-a07d-1de354ec2cce
if __name__ == '__main__':
    url = "https://api.seniverse.com/v3/life/suggestion.json?key=SkvZZVqAG5HrAotL3&location=shanghai&language=zh-Hans#"
    suggestionJson = requests.get(url).json()
    # print(json["results"][0]["suggestion"])
    suggestion = " ,感冒: " + suggestionJson["results"][0]["suggestion"]["flu"]["brief"] + "  紫外线: " + suggestionJson["results"][0]["suggestion"]["uv"]["brief"]
    # print(suggestion)

    suggestion = ""
    nullSuggestion = ""

    url = "https://api.seniverse.com/v3/weather/daily.json?key=SkvZZVqAG5HrAotL3&location=shanghai&language=zh-Hans&unit=c&start=0&days=5"
    json = requests.get(url).json()
    # print(json)
    # print(json["results"])
    # print(json["results"][0]["location"])
    # print(json["results"][0]["daily"])
    # print(json["results"][0]["daily"][0])
    # print(json["results"][0]["daily"][1])
    # print(json["results"][0]["daily"][2])
    # print(json["results"][0]["daily"][0]["text_day"])

    monitorWeather = MonitorWeather()

    '''雨 10~20 '''
    daily = 0
    date = "今天"
    keyWord = '雨'
    minCode = 10
    maxCode = 20
    extraWord = '请注意带伞，有雨 '
    monitorWeather.printText(daily, date, minCode, maxCode, extraWord, suggestion)

    daily = 1
    date = "明天"
    monitorWeather.printText(daily, date, minCode, maxCode, extraWord,nullSuggestion)

    daily = 2
    date = "后天"
    monitorWeather.printText(daily, date, minCode, maxCode, extraWord,nullSuggestion)

    '''雪'''
    daily = 0
    date = "今天"
    keyWord = '雪'
    minCode = 21
    maxCode = 25
    extraWord = '请注意带伞，要下雪了 '
    monitorWeather.printText(daily, date,minCode,maxCode, extraWord, suggestion)

    daily = 1
    date = "明天"
    monitorWeather.printText(daily, date,minCode,maxCode, extraWord, nullSuggestion)

    daily = 2
    date = "后天"
    monitorWeather.printText(daily, date,minCode,maxCode, extraWord, nullSuggestion)

    '''晴 0~8 '''
    daily = 0
    date = "今天"
    keyWord = '晴'
    minCode = 0
    maxCode = 8
    extraWord = '天气还阔以, '
    monitorWeather.printText(daily,date,minCode,maxCode,extraWord,suggestion)

    daily = 1
    date = "明天"
    monitorWeather.printText(daily, date,minCode,maxCode, extraWord,nullSuggestion)

    daily = 2
    date = "后天"
    monitorWeather.printText(daily, date,minCode,maxCode, extraWord,nullSuggestion)

    '''9	阴'''
    daily = 0
    date = "今天"
    minCode = 9
    maxCode = 9
    extraWord = '天气有点儿阴, '
    monitorWeather.printText(daily, date, minCode, maxCode, extraWord, suggestion)

    daily = 1
    date = "明天"
    monitorWeather.printText(daily, date, minCode, maxCode, extraWord, nullSuggestion)

    daily = 2
    date = "后天"
    monitorWeather.printText(daily, date, minCode, maxCode, extraWord, nullSuggestion)

    print(monitorWeather.result)

    monitorWeather.Url()
    monitorWeather.send()
