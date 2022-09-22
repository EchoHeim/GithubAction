## 1. 获取天气

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

``` bash
curl -o result.html wttr.in/Shenzhen
```

其他定制天气预报的格式和内容，详见它的[官方文档](https://github.com/chubin/wttr.in)

## 2. 发送邮件

拿到天气预报信息以后，只要放在邮件里面，发出去就可以了。

我用的是网易163邮件的免费发送服务，需要在邮箱设置中开启smtp服务。

![image](https://user-images.githubusercontent.com/26021085/191640816-0c0efede-d746-423a-aa3e-d0523363e0f8.png)

## 3. 配置 GitHubActions

详细配置[参考](https://github.com/EchoHeim/GithubAction/blob/master/.github/workflows/weather_bot.yml)

> 简单介绍一下获取天气与发送邮件部分

- shell脚本获取天气预报数据

``` yaml
    - name: 'Get Weather'
      run: bash ./Weather/weather.sh
```

上面代码中，run字段就是所要运行的命令。

- 发送邮件

``` yaml
    - name: 'Send mail'
      uses: dawidd6/action-send-mail@master
      with:
        server_address: smtp.163.com
        server_port: 465
        username: ${{ secrets.MAIL_USERNAME }}
        password: ${{ secrets.MAIL_PASSWORD }}
        subject: Weather Report
        body: file://result.html
        to: shilong.native@foxmail.com
        from: GitHub Actions
        content_type: text/html
```

上面代码中，发送邮件使用的是一个已经写好的 action，只要配几个参数就可以用。

参数之中，邮件 SMTP 服务器的用户名和密码，使用的是加密变量，需要在项目的settings/secrets菜单里面设置。

具体的语法解释可以参考[《GitHub Actions 入门教程》](https://github.com/EchoHeim/GithubAction/blob/master/GithubActions/README.md)。

其中用到的 action-send-mail 发送邮件服务的官方地址：<https://github.com/dawidd6/action-send-mail>

写好配置，推送到仓库以后，就可以每天清早收到一封天气预报邮件了。
