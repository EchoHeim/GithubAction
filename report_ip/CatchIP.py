import socket
import time
import timeout_decorator
import traceback

@timeout_decorator.timeout(4)
def get_host_ip():
    """
    查询本机ip地址
    :return:
    """
    ip='0.0.0.0'
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.connect(('8.8.8.8',80))
        print("start")
        ip=s.getsockname()[0]
    except:
        traceback.print_exc()
        print("error")
    finally:
        s.close()

    return ip

if __name__ == '__main__':
    print(get_host_ip())
