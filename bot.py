from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler, \
    ConversationHandler
from config import TOKEN, ADMIN_IDS
import sqlite3
from datetime import datetime, timedelta
import hashlib
import random
import string
import pytz
import logging

# 设置日志级别为DEBUG，并将日志同时输出到文件和控制台
logging.basicConfig(filename='bot.log', level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 创建一个Logger对象，用于记录日志
logger = logging.getLogger(__name__)

# 添加控制台处理程序，用于在控制台输出日志
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# 将日志保存为中文
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 全局变量，用于存储生成的卡密
global_card_key = None

WAITING_FOR_CARD_KEY = 1
WAITING_FOR_EXPIRATION_DAYS = 2


# 创建 "cards" 表格并初始化数据库
def create_table():
    conn = sqlite3.connect('cards.db')
    cursor = conn.cursor()
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY, card_key TEXT, card_key_hash TEXT, expiration_days INTEGER)')
    conn.commit()
    conn.close()


# 创建用户订阅信息表格并初始化数据库
def create_subscription_table():
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER PRIMARY KEY, expiration_date TEXT)')
    conn.commit()
    conn.close()


# 创建用于记录已使用卡密的表格并初始化数据库
def create_used_cards_table():
    conn = sqlite3.connect('used_cards.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS used_cards (id INTEGER PRIMARY KEY, card_key_hash TEXT)')
    conn.commit()
    conn.close()


# 将卡密和卡密哈希值以及卡密有效期保存到数据库
def save_card_key(card_key, expiration_days):
    card_key_hash = generate_hash(card_key)
    conn = sqlite3.connect('cards.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO cards (card_key, card_key_hash, expiration_days) VALUES (?, ?, ?)',
                   (card_key, card_key_hash, expiration_days))
    conn.commit()
    conn.close()


# 获取用户订阅信息
def get_subscription(user_id):
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('SELECT expiration_date FROM subscriptions WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


# 更新用户订阅信息
def update_subscription(user_id, expiration_date):
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiration_date) VALUES (?, ?)',
                   (user_id, expiration_date))
    conn.commit()
    conn.close()


# 辅助函数：生成卡密的哈希值
def generate_hash(card_key):
    sha256 = hashlib.sha256()
    sha256.update(card_key.encode())
    return sha256.hexdigest()


# 辅助函数：检查卡密哈希值是否存在于数据库中
def is_valid_card_key(card_key_hash):
    conn = sqlite3.connect('cards.db')
    cursor = conn.cursor()
    cursor.execute('SELECT card_key_hash FROM cards WHERE card_key_hash = ?', (card_key_hash,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


# 辅助函数：检查卡密是否已使用过
def is_used_card_key(card_key_hash):
    conn = sqlite3.connect('used_cards.db')
    cursor = conn.cursor()
    cursor.execute('SELECT card_key_hash FROM used_cards WHERE card_key_hash = ?', (card_key_hash,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


# 辅助函数：将卡密标记为已使用
def mark_card_key_as_used(card_key_hash):
    conn = sqlite3.connect('used_cards.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO used_cards (card_key_hash) VALUES (?)', (card_key_hash,))
    conn.commit()
    conn.close()


# 辅助函数：删除订阅用户的数据
def delete_subscription(user_id):
    conn = sqlite3.connect('subscriptions.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


# 处理/start命令
def start(update: Update, _: CallbackContext) -> None:
    show_buttons(update)
    # 记录/start命令的日志
    logger.info(f"用户 {update.message.chat.id} 发送了 /start 命令")


# 显示可视化按钮
def show_buttons(update: Update) -> None:
    keyboard = [
        [
            InlineKeyboardButton("订阅", callback_data='validate_subscription'),
            InlineKeyboardButton("更新", callback_data='check_subscription'),  # Modified button label
        ],
        [
            InlineKeyboardButton("查询到期时间", callback_data='check_subscription1'),
            InlineKeyboardButton("自助购买", url='https://a.cnqn.cc'),
        ],
        [
            InlineKeyboardButton("联系客服", url='https://t.me/Lime_68'),
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('代理更新机器人\n'
                              '30CNY一个月\n'
                              '七天左右更新一次\n'
                              '订阅成功后点击/start \n'
                              '点击更新按钮获取节点 \n'
                              '节点失效及时更新节点\n'
                              '节点仅限个人使用\n'
                              '禁止分享，发现永久拉黑\n'
                              '定制节点联系客服咨询\n'
                              , reply_markup=reply_markup)
    # 记录按钮显示的日志
    logger.debug(f"向用户 {update.message.chat.id} 显示了按钮")


# 处理按钮点击
def button_click(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    user_id = query.message.chat.id

    if query.data == 'validate_subscription':
        query.edit_message_text(text="请输入您的卡密")
        # 记录按钮点击的日志
        logger.info(f"用户 {user_id} 点击了 '订阅' 按钮")
        return WAITING_FOR_CARD_KEY
    elif query.data == 'check_subscription':
        # 检查用户的订阅状态
        expiration_date = get_subscription(user_id)
        if expiration_date:
            # 已订阅用户
            with open('dy.txt', 'r', encoding='utf-8') as file:
                content = file.read()
            query.edit_message_text(text=content)
        else:
            # 未订阅用户
            query.edit_message_text(text="请先进行订阅")


    elif query.data == 'check_subscription1':

        # 检查用户的订阅状态
        expiration_date = get_subscription(user_id)

        if expiration_date:
            query.edit_message_text(text=f"您的订阅到期时间：{expiration_date}")
        else:
            # 未订阅用户
            query.edit_message_text(text="请先进行订阅")

        # 记录按钮点击的日志
        logger.info(f"用户 {user_id} 点击了 '查询到期时间' 按钮")


# 处理用户输入的卡密
def handle_card_key(update: Update, context: CallbackContext) -> int:
    user_id = update.message.chat.id
    card_key = update.message.text
    card_key_hash = generate_hash(card_key)
    if is_valid_card_key(card_key_hash) and not is_used_card_key(card_key_hash):
        mark_card_key_as_used(card_key_hash)
        expiration_date = get_subscription(user_id)

        # 获取当前时间并设置时区为 "Asia/Shanghai"
        now = datetime.now(pytz.timezone('Asia/Shanghai'))

        if expiration_date:
            # 将到期日期转换为 datetime 对象并设置时区为 "Asia/Shanghai"
            expiration_date = datetime.strptime(expiration_date, '%Y-%m-%d %H:%M:%S').astimezone(
                pytz.timezone('Asia/Shanghai'))
            if expiration_date > now:
                # 如果当前到期日期还未过期，增加订阅时间
                new_expiration_date = add_subscription_days(expiration_date, 30)  # 默认增加30天订阅
            else:
                # 如果当前到期日期已过期，从当前时间开始增加订阅时间
                new_expiration_date = now + timedelta(days=30)
        else:
            # 如果用户没有有效的订阅，从当前时间开始增加订阅时间
            new_expiration_date = now + timedelta(days=30)

        # 将新的订阅到期日期保存到数据库
        update_subscription(user_id, new_expiration_date.strftime('%Y-%m-%d %H:%M:%S'))

        update.message.reply_text(text=f"订阅成功，订阅至 {new_expiration_date.strftime('%Y-%m-%d %H:%M:%S')}")
        # 记录用户订阅成功的日志
        logger.info(f"用户 {user_id} 订阅成功，订阅至 {new_expiration_date}")
    else:
        update.message.reply_text(text="卡密无效或已使用，请联系客服。")
        # 记录卡密无效的日志
        logger.warning(f"用户 {user_id} 提供了无效的卡密")
    return ConversationHandler.END


# 辅助函数：根据规则增加订阅天数
def add_subscription_days(date, days):
    return date + timedelta(days=days)


# /km 命令生成一个30天的卡密
def generate_card_key_command(update: Update, context: CallbackContext):
    if update.message.chat.id not in ADMIN_IDS:
        update.message.reply_text(text="只有管理员才能执行此操作")
        return
    card_key = generate_card_key()
    save_card_key(card_key, 30)
    update.message.reply_text(text=f"卡密已生成：{card_key}")


# 辅助函数：生成一个随机的卡密
def generate_card_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))


# 主函数
def main() -> None:
    create_table()
    create_subscription_table()
    create_used_cards_table()

    updater = Updater(TOKEN)

    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CallbackQueryHandler(button_click)],
        states={
            WAITING_FOR_CARD_KEY: [MessageHandler(Filters.text & ~Filters.command, handle_card_key)],
        },
        fallbacks=[],
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CommandHandler("km", generate_card_key_command))

    updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    main()
