## 目录文件说明

### AutoReportIP

使用 Python 发邮件自动上报本机 IP 地址

* linux 下运行 ip.sh；

    ``` bash
    ./ip.sh 
    ```

* CatchIP.py 可以直接获取当前 ip

    ``` python
    python3 CatchIP.py
    ```

    添加 timeout_decorator 超时退出功能，需要在 [Python packages](https://pypi.org/) 网站上下载 timeout_decorator 包，解压后安装使用 `python3 setup.py install` 

    添加异常处理，在没有获取到 IP 时，异常退出，返回默认 IP 变量 0.0.0.0

### 



