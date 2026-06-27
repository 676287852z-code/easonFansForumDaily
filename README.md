# easonFansForumDaily
自动完成神经研究所每日任务

## 文件说明
- dailyMission.py 保存了完成每日任务的脚本，包括签到、答题和摩天轮抽奖。

## 使用方法
fork本repositroy后，在Settings->Secrets中新建仓库密码（New repository secret）。
- 添加Name为`USERNAME`和`PASSWORD`的环境变量，分别添加自己神经研究所的账号和密码。
- 添加Name为`MAIL_USERNAME`和`MAIL_PASSWORD`的环境变量，分别添加自己邮箱的SMTP账号和密码。
- 如需使用LLM回答问题，需要在[硅基流动](https://cloud.siliconflow.cn/)申请 API Key，并添加`API_KEY`的环境变量，否则随机选择。
- 可选添加`MODEL_NAME`环境变量指定硅基流动模型，不设置时默认使用`deepseek-ai/DeepSeek-V3.2`；每道题会先联网搜索相关资料，再交给模型判断。如果搜索或指定模型不可用，脚本会自动尝试备用方案。
- `API_KEY`如果不需要也建议设置为0。
![tutorial1](img/tutorial1.png "tutorial1")
![tutorial2](img/tutorial2.png "tutorial2")

## 本地运行
1. Clone this repo and install prerequisites:

    ```bash
    # Clone this repo
    git clone git@github.com:TannerTam/easonFansForumDaily.git
    
    # Create a Conda environment
    conda create -n easonFansForumDaily python=3.10.0
    conda activate easonFansForumDaily
    
    # Install prequisites
    pip install -r requirements.txt
    # Install packages
    sudo apt update
    sudo apt install tesseract-ocr
    ```

2. 在本地新建`config.json`文件，内容为

    ```json
    {
        "USERNAME": "",
        "PASSWORD": "",
        "MAIL_USERNAME": "",
        "MAIL_PASSWORD": "",
        "API_KEY":"",
        "MODEL_NAME":"deepseek-ai/DeepSeek-V3.2"
    }
    ```
3. 在[网站](https://googlechromelabs.github.io/chrome-for-testing/#stable)下载与自己chrome版本相符合的chrome driver，并将文件夹解压后放到当前目录
4. 运行

    ```bash
    #无头
    python dailyMission.py --local --headless
    
    #显示窗口
    python dailyMission.py --local
    ```
