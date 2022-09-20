# 1. 获取天气

网站 [wttr.in](https://wttr.in/) 支持命令行请求天气预报。

``` bash
curl wttr.in
```
> 命令会返回当前 IP 地址所在位置的天气

它还允许 URL 里面指定城市。

``` bash
curl wttr.in/Shenzhen
```

返回的数据可以通过curl命令的-o参数，保存成文件，以便后面发送。

wttr. in 允许定制天气预报的格式和内容，详见它的文档，这里就不展开了

http://www.ruanyifeng.com/blog/2019/12/github_actions.html