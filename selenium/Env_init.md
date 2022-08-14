# GithubAction

# 1. 准备

- 在 <http://npm.taobao.org/mirrors/chromedriver/> 下载 chrome 驱动 chromedriver。

> 注意版本，可以先随便下载一个,我使用的是`104.0.5112.79`版本；
> 版本不匹配，运行会出错，查看log信息可得知当前使用chrome版本，然后下载对应版本的chromedriver替换即可。

- 建立`chrome`文件夹用来存放第一步下载后的chromedriver(linux版本)

- 建立文件夹`Spider`用来存放requirements.txt 和 test.py 文件

    - requirements.txt 
    
        ``` text
        requests==2.23.0
        lxml==4.5.1
        selenium==3.141.0
        ```

        > 用来安装python包
    
    -  test.py

        ``` py
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        import os

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chromedriver = "/usr/bin/chromedriver"
        os.environ["webdriver.chrome.driver"] = chromedriver
        driver = webdriver.Chrome(chrome_options=chrome_options,executable_path=chromedriver)
        driver.get("https://www.baidu.com")
        print(driver.title)
        driver.quit()
        ```

        > 用来测试

# 2. 部署

- 建立一个工作流

![image](https://user-images.githubusercontent.com/26021085/184545275-9fcc7b93-4835-4e51-a0b2-af0e9617e65b.png)

- 在左侧点击`New Workflow`,之后点击 `set up a workflow yourself`

![image](https://user-images.githubusercontent.com/26021085/184545391-ab1c548c-2d29-46e8-9d19-38c4784d7784.png)

- 创建 `.yml` 文件, 替换以下信息

``` yml
name: selenium

# Controls when the action will run. 
on:
  # Triggers the workflow on push or pull request events but only for the main branch
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
  # Allows you to run this workflow manually from the Actions tab
  workflow_dispatch:

# A workflow run is made up of one or more jobs that can run sequentially or in parallel
jobs:
  # This workflow contains a single job called "build"
  build:
    # The type of runner that the job will run on
    runs-on: ubuntu-latest

    # Steps represent a sequence of tasks that will be executed as part of the job
    steps:
      # Checks-out your repository under $GITHUB_WORKSPACE, so your job can access it
      - name: Checkout
        uses: actions/checkout@v2

      # Runs a single command using the runners shell
      - name: 'Set up Python'
        uses: actions/setup-python@v1
        with:
           python-version: 3.7
      - name: 'Install requirements'
        run: pip install -r ./Spider/requirements.txt
      - name: 'Working'
        run: |
          sudo cp -p ./chrome/chromedriver /usr/bin/
          chmod -R 777 /usr/bin/chromedriver
          python ./Spider/test.py
```

- 提交 commit 后，运行此工作流

![image](https://user-images.githubusercontent.com/26021085/184545499-57331f38-0764-422e-becd-df4690d95012.png)

- 查看运行结果

![image](https://user-images.githubusercontent.com/26021085/184545543-df8f65b7-b6e4-4880-815a-93be70e1e6f8.png)

没有错误，打印信息和预想的一样，成功！
