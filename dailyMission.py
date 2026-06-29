from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from time import sleep
import re
import os
import argparse
import json
import time
from PIL import Image
from io import BytesIO
import pytesseract
import base64
import shutil

import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
import io
import sys
from functools import partial
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from ddgs import DDGS  # 保留但不再使用（可选择删除）
from openai import OpenAI
from urllib.parse import urljoin
import random

username = None
password = None
mail_user = None
mail_pass = None
api_key = None
model_name = None

# ---------- 修改点 1：默认模型和备选模型改为豆包 ----------
DEFAULT_MODEL_NAME = "doubao-seed-2-1-pro-260628"  # 支持联网搜索的模型
FALLBACK_MODEL_NAMES = [
    "doubao-seed-2-1-pro-260628",
    "doubao-pro-32k",
]

QUIZ_LOG_PATH = os.environ.get("QUIZ_LOG_PATH", "quiz_results.jsonl")
_last_answer_model = None
FAN_MESSAGES = [
    "今天也要好好听歌，祝你开心。",
    "愿你今天有首好歌陪着。",
    "打卡路过，祝你今天顺顺利利。",
    "今天也一起喜欢陈奕迅。",
    "愿音乐和好心情都在你身边。",
    "路过留一句，祝你今日愉快。",
    "听歌愉快，生活也要闪闪发光。",
    "今天也要保持热爱呀。",
    "祝你今天拥有好天气和好歌单。",
    "歌迷路过，送上一点好心情。",
]

# ---------- 以下函数均未改动 ----------
def login(driver):
    try:
        driver.get("https://www.easonfans.com/FORUM/member.php?mod=logging&action=login")
        time.sleep(1)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.NAME, "loginsubmit").click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "umLogin"))
        )
        print("登录成功！")
        return True
    except Exception as e:
        print(f"登录过程中出现错误")
        return False

def signin(driver):
    driver.get("https://www.easonfans.com/forum/plugin.php?id=dsu_paulsign:sign")
    try:
        badge_element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "fwin_badgewin_7ree"))
        )
        if badge_element:
            print("徽章弹窗出现，准备领取徽章。")
            driver.get("https://www.easonfans.com/forum/plugin.php?id=badge_7ree:badge_7ree&code=1")
            buttons = WebDriverWait(driver, 10).until(
                lambda current_driver: current_driver.find_elements(
                    By.CSS_SELECTOR, 'a[href*="plugin.php?id=badge_7ree"]'
                )
            )
            button = next(
                (candidate for candidate in buttons if candidate.is_displayed() and candidate.is_enabled()),
                buttons[-1],
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            sleep(1)
            before_click_content = driver.page_source
            try:
                button.click()
            except Exception:
                print("徽章按钮普通点击失败，使用备用点击方式。")
                driver.execute_script("arguments[0].click();", button)
            try:
                WebDriverWait(driver, 5).until(
                    lambda current_driver: current_driver.page_source != before_click_content
                )
            except TimeoutException:
                pass
            after_click_content = driver.page_source
            if before_click_content != after_click_content:
                print("徽章领取成功！")
            else:
                print("未确认徽章领取结果，继续执行每日任务。")
    except TimeoutException:
        print("没有徽章弹窗。")
    except Exception as error:
        print(f"徽章领取出现错误（{type(error).__name__}），已跳过并继续执行每日任务。")
    
    driver.get("https://www.easonfans.com/forum/plugin.php?id=dsu_paulsign:sign")
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//h1[contains(text(), '您今天已经签到过了或者签到时间还未开始')]"))
        )
        print("今天已签到或签到未开始。")
    except TimeoutException:
        try:
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[@onclick=\"showWindow('qwindow', 'qiandao', 'post', '0');return false\"]"))
            )
            li_element = driver.find_element(By.ID, "kx")
            li_element.click()
            radio_button = driver.find_element(By.CSS_SELECTOR, "input[type='radio'][name='qdmode'][value='3']")
            radio_button.click()
            link = driver.find_element(By.XPATH, "//a[@onclick=\"showWindow('qwindow', 'qiandao', 'post', '0');return false\"]")
            link.click()
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//h1[contains(text(), '您今天已经签到过了或者签到时间还未开始')]"))
                )
                print("签到成功！")
            except TimeoutException:
                print("签到失败。")
        except Exception as e:
            print(f"签到过程中出现错误。")

def extract_quiz_stats(page_source):
    answered_match = re.search(r"累计答题:\s*(\d+)", page_source)
    correct_match = re.search(r"累计答对:\s*(\d+)", page_source)
    answered = int(answered_match.group(1)) if answered_match else None
    correct = int(correct_match.group(1)) if correct_match else None
    return answered, correct

def append_quiz_record(record):
    with open(QUIZ_LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")

# ---------- 删除原有的 search_question_context 函数，不再需要 ----------

def question(driver):
    base_url = "https://www.easonfans.com/forum/plugin.php?id=ahome_dayquestion:index"
    global _api_call_count
    _api_call_count = 0
    MAX_API_CALLS = 3

    with open(QUIZ_LOG_PATH, "w", encoding="utf-8"):
        pass

    driver.get(base_url)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "inner"))
        )
    except Exception as e:
        print(f"页面加载失败: {e}")

    try:
        page_source = driver.page_source
        total_answered_match = re.search(r"累计答题:\s*(\d+)", page_source)
        total_correct_match = re.search(r"累计答对:\s*(\d+)", page_source)
        initial_answer = int(total_answered_match.group(1)) if total_answered_match else 0
        initial_correct = int(total_correct_match.group(1)) if total_correct_match else 0
    except Exception as e:
        print(f"无法提取初始答题信息: {e}")
        initial_answer = 0
        initial_correct = 0

    previous_participated = -1
    while True:
        driver.get(base_url)
        try:
            participated_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "inner"))
            )
        except Exception as e:
            print(f"页面加载失败: {e}")
            break

        matches = re.search(r"\((\d+)/(\d+)\)", participated_element.text)
        participated, total = map(int, matches.groups())
        if previous_participated >= 0 and participated == previous_participated + 1:
            _api_call_count = 0
        previous_participated = participated

        if participated >= total:
            try:
                page_source = driver.page_source
                total_answered_match = re.search(r"累计答题:\s*(\d+)", page_source)
                total_correct_match = re.search(r"累计答对:\s*(\d+)", page_source)
                final_answer = int(total_answered_match.group(1)) if total_answered_match else 0
                final_correct = int(total_correct_match.group(1)) if total_correct_match else 0
            except Exception as e:
                print(f"无法提取最终答题信息: {e}")
                final_answer = initial_answer
                final_correct = initial_correct
            
            if final_answer != initial_answer and initial_answer != 0:
                correct_rate = (final_correct - initial_correct)/(final_answer-initial_answer)
                correct_rate_percent = correct_rate * 100
                print(f"今日答题已完成，答题正确率 {correct_rate_percent:.2f}%。总正确数/答题数：{final_correct}/{final_answer}。")
            else:
                print(f"今日答题已完成。总正确数/答题数：{final_correct}/{final_answer}。")
            break
        
        if _api_call_count >= MAX_API_CALLS:
            print(f"单次运行 API 调用已达 {MAX_API_CALLS} 次，跳过后续答题")
            break
        
        try:
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@name='submit'][@value='true']"))
            )
            answer_question(driver, participated, _api_call_count)
        except Exception as e:
            print(f"答题第{participated+1}题过程中出现错误，正在重试。")
            sleep(5)
            continue

def answer_question(driver, question_number, option_index=0):
    """答一题：调用豆包 API（自带联网搜索）"""
    prompt, prompt_options = build_prompt(driver)
    question_text = prompt.split("\n\n选项：", 1)[0].replace("题目：", "", 1).strip()
    before_answered, before_correct = extract_quiz_stats(driver.page_source)

    print(f"[答题] 第 {question_number + 1} 题：{question_text}")
    for option_label, option_text in prompt_options:
        print(f"[答题] {option_label}: {option_text}")

    # ---------- 修改点 2：不再手动搜索，直接调用 API ----------
    # search_results = search_question_context(question_text, prompt_options)  # 已删除
    label = get_answer_from_api(prompt)   # 模型自带联网搜索
    option_labels = ['a1', 'a2', 'a3', 'a4']
    if label is None:
        label = option_labels[option_index % len(option_labels)]
        print(f"API 返回异常，使用备选选项（第 {option_index + 1} 次）: {label}")
    model_label = label
    selected_text = dict(prompt_options).get(label)
    if selected_text:
        current_options = extract_question_options(driver)
        current_label = next((item_label for item_label, text in current_options if text == selected_text), None)
        if current_label:
            label = current_label
        else:
            print("未能在当前页面匹配到原选项文字，继续使用原选项标签。")
    clicked_text = dict(extract_question_options(driver)).get(label, selected_text)
    print(
        f"[答题] 模型={_last_answer_model or 'fallback'}，"
        f"模型选择={model_label}，实际点击={label}: {clicked_text or '未知'}"
    )

    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, label))).click()
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[@name='submit'][@value='true']"))
    ).click()

    try:
        WebDriverWait(driver, 10).until(
            lambda d: extract_quiz_stats(d.page_source)[0] not in (None, before_answered)
        )
    except TimeoutException:
        sleep(2)

    after_answered, after_correct = extract_quiz_stats(driver.page_source)
    if (
        before_correct is not None
        and after_correct is not None
        and after_correct > before_correct
    ):
        result = "正确"
    elif (
        before_answered is not None
        and after_answered is not None
        and after_answered > before_answered
    ):
        result = "错误"
    else:
        result = "未知"

    # 日志中 search_results 留空（因为不再手动搜索）
    record = {
        "time": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "question_number": question_number + 1,
        "question": question_text,
        "options": dict(prompt_options),
        "search_results": [],  # 不再使用手动搜索结果
        "model": _last_answer_model or "fallback",
        "model_choice": model_label,
        "clicked_label": label,
        "clicked_text": clicked_text,
        "result": result,
        "answered_before": before_answered,
        "answered_after": after_answered,
        "correct_before": before_correct,
        "correct_after": after_correct,
    }
    append_quiz_record(record)
    print(f"[答题] 第 {question_number + 1} 题结果：{result}")

def extract_question_options(driver):
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    options = []
    option_divs = soup.find_all('div', class_='qs_option')
    for div in option_divs:
        input_tag = div.find('input')
        label = input_tag.get('id') if input_tag else 'unknown'
        raw_text = div.get_text(strip=True).replace('\xa0', ' ')
        text = raw_text.split(' ', 1)[-1] if ' ' in raw_text else raw_text
        options.append((label, text))
    return options

def build_prompt(driver):
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    b_tag = soup.find('b', string=lambda s: s and '【题目】' in s)
    parent_tag = b_tag.parent
    full_text = parent_tag.get_text(separator='', strip=True)
    full_text = full_text.replace('【题目】', '').replace('\xa0', ' ').strip()
    options = extract_question_options(driver)
    prompt = f"题目：{full_text}\n\n选项：\n"
    for label, text in options:
        prompt += f"{label}. {text}\n"
    prompt += "\n请认真判断题目和四个选项，只能从 a1、a2、a3、a4 中选择一个最可能正确的答案。只返回选项标签，不要解释。"
    return prompt, options

# ---------- 修改点 3：核心 API 函数改为豆包 ----------
def get_answer_from_api(prompt, search_results=None):
    """调用豆包 API（自带联网搜索），返回 a1-a4 或 None"""
    global _api_call_count, _last_answer_model
    _api_call_count += 1
    _last_answer_model = None

    if not api_key or api_key == "0":
        print("API_KEY 未配置，使用备选选项。")
        return None

    # 豆包 API 地址（从你的 curl 示例获取）
    base_url = 'https://ark.cn-beijing.volces.com/api/v3'
    client = OpenAI(api_key=api_key, base_url=base_url)
    valid_options = ['a1', 'a2', 'a3', 'a4']

    # 候选模型：优先使用用户指定的，否则使用默认支持联网的模型
    candidate_models = []
    if model_name:
        candidate_models.append(model_name)
    if not candidate_models:
        candidate_models.append(DEFAULT_MODEL_NAME)  # 使用默认豆包模型
    # 追加备选（去重）
    candidate_models.extend(FALLBACK_MODEL_NAMES)
    candidate_models = list(dict.fromkeys(candidate_models))

    response = None
    last_error = None

    for candidate_model in candidate_models:
        try:
            response = client.chat.completions.create(
                model=candidate_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个中文选择题答题助手。这是陈奕迅粉丝网站神经研究所每日单选题，联网搜索论坛题库、歌词、专辑资料，只输出正确选项，不要多余解释"
                            "你可以使用联网搜索功能获取最新信息来辅助判断。"
                            "只能输出 a1、a2、a3、a4 其中一个标签，不要输出任何解释。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=32,
                enable_web_search=True,          # 关键：开启联网搜索
                # reasoning_effort="high",       # 可选，根据模型支持
            )
            _last_answer_model = candidate_model
            print(f"API 使用模型: {candidate_model} (联网搜索已启用)")
            break
        except Exception as e:
            last_error = e
            print(f"模型 {candidate_model} 调用失败（{type(e).__name__}），尝试下一个模型。")

    if response is None:
        print(f"API 调用失败: {last_error}")
        return None

    # 解析响应（保持不变）
    raw_text = None
    if hasattr(response, 'choices') and response.choices:
        raw_text = getattr(response.choices[0].message, 'content', None) or getattr(response.choices[0], 'content', None)
    elif hasattr(response, 'output') and hasattr(response.output, 'text'):
        raw_text = response.output.text
    elif hasattr(response, 'output_text'):
        raw_text = response.output_text
    if not raw_text:
        print("API 未返回有效内容")
        return None

    match = re.search(r'\ba[1-4]\b', raw_text)
    label = (match.group(0).strip() if match else None)
    if label and label in valid_options:
        print(f"API 返回的答案标签: {label}")
        return label
    print(f"API 未返回有效结果或结果不在合法选项中（{raw_text[:50] if raw_text else '无'}...）")
    return None

# ---------- 以下函数均未改动 ----------
def check_free_lottery(driver):
    driver.get("https://www.easonfans.com/forum/plugin.php?id=gplayconstellation:front")
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//span[contains(text(), '今日剩余免费次数：0次')]"))
        )
        return False
    except:
        return True

def lottery(driver):
    if not check_free_lottery(driver):
        print("今天已免费抽奖。")
        return
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "pointlevel"))
        ).click()
        print("开始免费抽奖。")
        sleep(5)
        if not check_free_lottery(driver):
            print("免费抽奖成功！")
        else:
            print("免费抽奖失败。")
    except Exception as e:
        print(f"抽奖过程中出现错误。")

def getMoney(driver):
    driver.get("https://www.easonfans.com/forum/home.php?mod=spacecp&ac=credit&showcredit=1")
    try:
        money_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//li[@class='xi1 cl']"))
        )
        money_text = money_element.text
        money_amount = [int(s) for s in money_text.split() if s.isdigit()][0]
        return money_amount
    except Exception as e:
        print(f"获取金钱失败。")
        return 0

def extract_friend_links(driver):
    friends = []
    seen_uids = set()
    friend_list_urls = [
        "https://www.easonfans.com/forum/home.php?mod=space&do=friend",
        "https://www.easonfans.com/forum/home.php?mod=space&do=friend&view=me",
        "https://www.easonfans.com/forum/home.php?mod=space&do=friend&view=all",
    ]
    for friend_list_url in friend_list_urls:
        driver.get(friend_list_url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception as e:
            print(f"好友列表加载失败: {friend_list_url} - {e}")
            continue
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href']
            uid_match = re.search(r'(?:uid=|space-uid-)(\d+)', href)
            if not uid_match:
                continue
            uid = uid_match.group(1)
            if uid in seen_uids:
                continue
            name = link.get_text(strip=True) or f"UID {uid}"
            seen_uids.add(uid)
            friends.append({
                "uid": uid,
                "name": name,
                "url": urljoin(driver.current_url, href),
            })
    print(f"好友列表提取到 {len(friends)} 个候选好友。")
    return friends

def leave_wall_message(driver, friend, message):
    wall_urls = [
        f"https://www.easonfans.com/forum/home.php?mod=space&uid={friend['uid']}&do=wall",
        f"https://www.easonfans.com/forum/home.php?mod=space&uid={friend['uid']}&do=wall&view=me",
        friend["url"],
    ]
    for wall_url in wall_urls:
        driver.get(wall_url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            continue
        textareas = driver.find_elements(
            By.CSS_SELECTOR,
            "textarea, textarea[name='message'], textarea#message, textarea[name='comments']"
        )
        inputs = driver.find_elements(
            By.CSS_SELECTOR,
            "input[type='text'], input[name='message'], input#message"
        )
        message_box = next((item for item in textareas + inputs if item.is_displayed() and item.is_enabled()), None)
        if not message_box:
            print(f"好友 {friend['name']} 页面未找到可用留言框: {wall_url}")
            continue
        message_box.clear()
        message_box.send_keys(message)
        submit_buttons = driver.find_elements(
            By.XPATH,
            "//button[@type='submit' or @id='commentsubmit_btn' or @name='commentsubmit' or contains(., '留言') or contains(., '提交') or contains(., '发表')]"
        )
        submit_buttons += driver.find_elements(
            By.XPATH,
            "//input[@type='submit' or @type='button' or @id='commentsubmit_btn' or @name='commentsubmit']"
        )
        submit_button = next((item for item in submit_buttons if item.is_displayed() and item.is_enabled()), None)
        if not submit_button:
            print(f"好友 {friend['name']} 页面未找到提交按钮: {wall_url}")
            continue
        driver.execute_script("arguments[0].click();", submit_button)
        sleep(random.randint(10, 15))
        print(f"已给好友 {friend['name']} 留言: {message}")
        return True
    print(f"未找到好友 {friend['name']} 的留言入口，已跳过。")
    return False

def leave_friend_messages(driver, limit=7):
    try:
        friends = extract_friend_links(driver)
        if not friends:
            print("未找到好友，跳过好友留言。")
            return
        random.shuffle(friends)
        sent_count = 0
        for friend in friends:
            if sent_count >= limit:
                break
            message = random.choice(FAN_MESSAGES)
            if leave_wall_message(driver, friend, message):
                sent_count += 1
                sleep(random.randint(10, 20))
        print(f"好友留言完成，本次成功留言 {sent_count} 人。")
    except Exception as e:
        print(f"好友留言过程中出现错误: {e}")

def sendEmail(msg):
    sender = receiver = mail_user
    message = MIMEText(msg, 'plain', 'utf-8')
    message['From'] = formataddr(("Daily mission Assitance", sender))
    message['To'] = formataddr(("Tanner", receiver))
    message['Subject'] = Header('签到脚本运行报告', 'utf-8')
    try:
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(mail_user, mail_pass)
        server.sendmail(sender, [receiver], message.as_string())
        print("邮件发送成功。")
        server.quit()
    except smtplib.SMTPException as e:
        print(f"邮件发送失败。")

class TeeOutput:
    def __init__(self, console, buffer):
        self.console = console
        self.buffer = buffer
    def write(self, data):
        self.console.write(data)
        self.buffer.write(data)
    def flush(self):
        self.console.flush()
        self.buffer.flush()

def capture_output(func, tee=False):
    buffer = io.StringIO()
    if tee:
        sys.stdout = TeeOutput(sys.__stdout__, buffer)
    else:
        sys.stdout = buffer
    try:
        func()
    finally:
        sys.stdout = sys.__stdout__
    return buffer.getvalue()

def merge(headless: bool, local: bool, chromedriver_path: str):
    global username, password, mail_user, mail_pass
    chrome_options = webdriver.ChromeOptions()
    if headless:
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-background-networking')
    chrome_options.add_argument('--disable-sync')
    chrome_options.add_argument('--disable-default-apps')
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    beijing_tz = timezone(timedelta(hours=8))
    now_str = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")
    if local:
        print(f"=== Script for {username} started at {now_str} locally===")
    else:
        print(f"=== Script for {username} started at {now_str} remotely===")

    login_success = False
    while not login_success:
        login_success = login(driver)
        if login_success:
            break
        else:
            print("重新尝试登录...")
            sleep(5)
    initial_money = getMoney(driver)
    signin(driver)
    question(driver)
    lottery(driver)
    leave_friend_messages(driver)
    final_money = getMoney(driver)
    print(f"金钱变化：{initial_money} -> {final_money}。")
    driver.quit()

def main():
    global username, password, mail_user, mail_pass, api_key, model_name
    parser = argparse.ArgumentParser()
    parser.add_argument('--local', action='store_true', help='Use local config and chromedriver path')
    parser.add_argument('--headless', action='store_true', help='Enable headless mode')
    args = parser.parse_args()
    try:
        if args.local:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            linux_driver_dir = os.path.join(base_dir, "chromedriver-linux64")
            win_driver_dir = os.path.join(base_dir, "chromedriver-win64")
            if os.path.exists(linux_driver_dir):
                chromedriver_path = os.path.join(linux_driver_dir, "chromedriver")
            elif os.path.exists(win_driver_dir):
                chromedriver_path = os.path.join(win_driver_dir, "chromedriver.exe")
            else:
                raise FileNotFoundError("未找到 chromedriver-linux64 或 chromedriver-win64 文件夹")
            config_path = os.path.join(base_dir, "config.json")
            with open(config_path, 'r') as f:
                config = json.load(f)
            username = config['USERNAME']
            password = config['PASSWORD']
            mail_user = config['MAIL_USERNAME']
            mail_pass = config['MAIL_PASSWORD']
            api_key = config['API_KEY']
            model_name = config.get('MODEL_NAME', DEFAULT_MODEL_NAME)
        else:
            chromedriver_path = shutil.which("chromedriver")
            username = os.environ['USERNAME']
            password = os.environ['PASSWORD']
            mail_user = os.environ['MAIL_USERNAME']
            mail_pass = os.environ['MAIL_PASSWORD']
            api_key = os.environ['API_KEY']
            model_name = os.environ.get('MODEL_NAME', DEFAULT_MODEL_NAME)
    except KeyError as e:
        raise Exception(f"Missing required configuration: {e}")

    merge_fn = partial(merge, headless=args.headless, local=args.local, chromedriver_path=chromedriver_path)
    output_message = capture_output(merge_fn, tee=True)
    sendEmail(output_message)

if __name__ == '__main__':
    main()
