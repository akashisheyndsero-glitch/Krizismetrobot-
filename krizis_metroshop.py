import os
import logging
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =====================================================
# НАСТРОЙКИ
# =====================================================

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MANAGER = "Menagerkrizis"

DB_NAME = "krizis_orders.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# =====================================================
# ТОВАРЫ
# =====================================================

PRODUCTS = {
    "m5_5": {
        "name": "5 карта — вынос 5кк",
        "price": 30,
        "gifts": 2,
        "category": "currency",
    },
    "m7_5": {
        "name": "7 карта — вынос 5кк",
        "price": 15,
        "gifts": 1,
        "category": "currency",
    },
    "m5_8": {
        "name": "5 карта — вынос 7/8кк",
        "price": 45,
        "gifts": 3,
        "category": "currency",
    },
    "m7_8": {
        "name": "7 карта — вынос 7/8кк",
        "price": 30,
        "gifts": 2,
        "category": "currency",
    },
    "f6": {
        "name": "Полный сет Ф6",
        "details": "Шлем ОБ/КР/СФ, броня ОБ/КР/СФ и рюкзак",
        "price": 15,
        "gifts": 1,
        "category": "items",
    },
    "guns": {
        "name": "МК14 ВК + МГ3 ВК",
        "details": "Включая обвесы",
        "price": 15,
        "gifts": 1,
        "category": "items",
    },
}


# =====================================================
# БАЗА ДАННЫХ
# =====================================================

def db_connect():
    con = sqlite3.connect(DB_NAME)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db_connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                payment TEXT NOT NULL,
                status TEXT NOT NULL,
                created TEXT NOT NULL,
                telegram_charge_id TEXT
            )
        """)


def create_order(user, product_id, payment):
    product = PRODUCTS[product_id]

    with db_connect() as con:
        cur = con.execute("""
            INSERT INTO orders (
                user_id, username, product_id,
                product_name, price, payment,
                status, created
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user.id,
            user.username or "нет username",
            product_id,
            product["name"],
            product["price"],
            payment,
            "Ожидает оплаты" if payment == "stars"
            else "Ожидает подтверждения подарка",
            datetime.now().strftime("%d.%m.%Y %H:%M"),
        ))

        return cur.lastrowid


def get_order(order_id):
    with db_connect() as con:
        return con.execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()


def set_order_status(order_id, status, charge_id=None):
    with db_connect() as con:
        con.execute("""
            UPDATE orders
            SET status = ?,
                telegram_charge_id =
                COALESCE(?, telegram_charge_id)
            WHERE id = ?
        """, (status, charge_id, order_id))


def get_user_orders(user_id):
    with db_connect() as con:
        return con.execute("""
            SELECT * FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 10
        """, (user_id,)).fetchall()


def get_recent_orders(limit=20):
    with db_connect() as con:
        return con.execute("""
            SELECT * FROM orders
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()


# =====================================================
# КЛАВИАТУРЫ
# =====================================================

def home_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "💰 Вынос валюты",
            callback_data="catalog:currency"
        )],
        [InlineKeyboardButton(
            "🛡 Вещи",
            callback_data="catalog:items"
        )],
        [InlineKeyboardButton(
            "📦 Мои заказы",
            callback_data="my_orders"
        )],
        [InlineKeyboardButton(
            "👨‍💼 Написать менеджеру",
            url=f"https://t.me/{MANAGER}"
        )],
    ])


def catalog_keyboard(category):
    rows = []

    for product_id, product in PRODUCTS.items():
        if product["category"] == category:
            rows.append([
                InlineKeyboardButton(
                    f'{product["name"]} — {product["price"]}⭐',
                    callback_data=f"product:{product_id}"
                )
            ])

    rows.append([
        InlineKeyboardButton(
            "⬅️ Назад",
            callback_data="home"
        )
    ])

    return InlineKeyboardMarkup(rows)


def payment_keyboard(product_id):
    product = PRODUCTS[product_id]

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f'⭐ Оплатить {product["price"]} Stars',
            callback_data=f"pay:{product_id}:stars"
        )],
        [InlineKeyboardButton(
            f'🎁 Оплата подарками ({product["gifts"]} шт.)',
            callback_data=f"pay:{product_id}:gift"
        )],
        [InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"catalog:{product['category']}"
        )],
    ])


# =====================================================
# ВСПОМОГАТЕЛЬНОЕ
# =====================================================

def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID


async def notify_admin(context, message):
    if ADMIN_ID == 0:
        return

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=message
        )
    except Exception:
        logger.exception("Ошибка отправки администратору")


# =====================================================
# START
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🔥 KRIZIS METROSHOP 🔥\n\n"
        "PUBG MOBILE • METRO ROYALE\n\n"
        "Выбери нужную услугу:",
        reply_markup=home_keyboard()
    )


# =====================================================
# ОБРАБОТКА КНОПОК
# =====================================================

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "home":
        await query.edit_message_text(
            "🔥 KRIZIS METROSHOP\n\nВыбери раздел:",
            reply_markup=home_keyboard()
        )
        return

    if data.startswith("catalog:"):
        category = data.split(":")[1]

        if category == "currency":
            title = "💰 ВЫНОС МЕТРОВАЛЮТЫ\n\nВыбери услугу:"
        elif category == "items":
            title = (
                "🛡 ВЕЩИ\n\n"
                "Золото — ❌ нет в наличии\n\n"
                "Выбери товар:"
            )
        else:
            await query.edit_message_text("Раздел не найден.")
            return

        await query.edit_message_text(
            title,
            reply_markup=catalog_keyboard(category)
        )
        return

    if data.startswith("product:"):
        product_id = data.split(":")[1]
        product = PRODUCTS.get(product_id)

        if not product:
            await query.edit_message_text("Товар не найден.")
            return

        description = product.get("details", "")

        text = (
            f'🛒 {product["name"]}\n\n'
            f'💰 Цена: {product["price"]}⭐\n'
            f'🎁 Альтернатива: {product["gifts"]} подарков 🧸 или 💝\n'
        )

        if description:
            text += f"\n📋 {description}\n"

        text += "\nВыбери способ оплаты:"

        await query.edit_message_text(
            text,
            reply_markup=payment_keyboard(product_id)
        )
        return

    if data.startswith("pay:"):
        parts = data.split(":")

        if len(parts) != 3:
            return

        product_id = parts[1]
        payment = parts[2]

        product = PRODUCTS.get(product_id)

        if not product or payment not in ("stars", "gift"):
            await query.edit_message_text("Ошибка выбора.")
            return

        order_id = create_order(
            query.from_user,
            product_id,
            payment
        )

        username = query.from_user.username or "нет username"

        if payment == "gift":
            await query.edit_message_text(
                f"🎁 ЗАКАЗ №{order_id}\n\n"
                f'Товар: {product["name"]}\n'
                f'Оплата: {product["gifts"]} подарков 🧸 или 💝\n\n'
                f"Для оплаты напиши менеджеру @{MANAGER}.\n"
                "Заказ начнут выполнять после проверки оплаты.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "👨‍💼 Написать менеджеру",
                        url=f"https://t.me/{MANAGER}"
                    )],
                    [InlineKeyboardButton(
                        "🏠 Главное меню",
                        callback_data="home"
                    )],
                ])
            )

            await notify_admin(
                context,
                f"🎁 НОВЫЙ ЗАКАЗ №{order_id}\n\n"
                f"Покупатель: @{username}\n"
                f"ID: {query.from_user.id}\n"
                f'Товар: {product["name"]}\n'
                f'Нужно подарков: {product["gifts"]}\n'
                "Статус: ожидает подтверждения подарка\n\n"
                f"После проверки используй /giftpaid {order_id}"
            )
            return

        await query.edit_message_text(
            f"⏳ Заказ №{order_id} создан.\n\n"
            "Открываю оплату Telegram Stars..."
        )

        try:
            await context.bot.send_invoice(
                chat_id=query.from_user.id,
                title="KRIZIS METROSHOP",
                description=product["name"],
                payload=f"krizis_order_{order_id}",
                provider_token="",
                currency="XTR",
                prices=[
                    LabeledPrice(
                        product["name"],
                        product["price"]
                    )
                ]
            )

        except Exception:
            logger.exception("Ошибка создания счёта")

            set_order_status(
                order_id,
                "Ошибка создания счёта"
            )

            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=f"Не удалось создать счёт. Напиши @{MANAGER}."
            )

        return

    if data == "my_orders":
        orders = get_user_orders(query.from_user.id)

        if not orders:
            await query.edit_message_text(
                "📦 У тебя пока нет заказов.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data="home"
                    )]
                ])
            )
            return

        lines = ["📦 ТВОИ ПОСЛЕДНИЕ ЗАКАЗЫ\n"]

        for order in orders:
            lines.append(
                f'№{order["id"]} — {order["product_name"]}\n'
                f'Цена: {order["price"]}⭐\n'
                f'Статус: {order["status"]}\n'
            )

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "⬅️ Назад",
                    callback_data="home"
                )]
            ])
        )


# =====================================================
# ПРОВЕРКА STARS
# =====================================================

async def precheckout_handler(update, context):
    query = update.pre_checkout_query

    try:
        prefix = "krizis_order_"

        if not query.invoice_payload.startswith(prefix):
            await query.answer(
                ok=False,
                error_message="Неизвестный заказ."
            )
            return

        order_id = int(
            query.invoice_payload[len(prefix):]
        )

        order = get_order(order_id)

        if (
            order is None
            or order["user_id"] != query.from_user.id
            or order["payment"] != "stars"
            or order["status"] != "Ожидает оплаты"
            or query.currency != "XTR"
            or query.total_amount != order["price"]
        ):
            await query.answer(
                ok=False,
                error_message="Заказ недоступен."
            )
            return

        await query.answer(ok=True)

    except Exception:
        logger.exception("Ошибка проверки оплаты")

        await query.answer(
            ok=False,
            error_message="Ошибка проверки заказа."
        )


# =====================================================
# УСПЕШНАЯ ОПЛАТА
# =====================================================

async def successful_payment_handler(update, context):
    payment = update.message.successful_payment

    try:
        prefix = "krizis_order_"

        if not payment.invoice_payload.startswith(prefix):
            return

        order_id = int(
            payment.invoice_payload[len(prefix):]
        )

        order = get_order(order_id)

        if (
            order is None
            or order["user_id"] != update.effective_user.id
            or order["payment"] != "stars"
            or order["status"] != "Ожидает оплаты"
            or payment.currency != "XTR"
            or payment.total_amount != order["price"]
        ):
            logger.warning("Несовпадение данных оплаты")
            return

        set_order_status(
            order_id,
            "Оплачено",
            payment.telegram_payment_charge_id
        )

        await update.message.reply_text(
            f"✅ ОПЛАТА ПОЛУЧЕНА!\n\n"
            f"Заказ №{order_id}\n"
            f'Товар: {order["product_name"]}\n\n'
            "Заказ передан менеджеру. Ожидай связи."
        )

        await notify_admin(
            context,
            f"💰 ОПЛАТА ПОЛУЧЕНА!\n\n"
            f"Заказ №{order_id}\n"
            f"Покупатель: @{order['username']}\n"
            f"ID: {order['user_id']}\n"
            f'Товар: {order["product_name"]}\n'
            f"Оплата: {payment.total_amount} Stars\n"
            "Статус: оплачено\n\n"
            f"Завершить: /done {order_id}"
        )

    except Exception:
        logger.exception("Ошибка обработки оплаты")


# =====================================================
# АДМИН-ПАНЕЛЬ
# =====================================================

async def admin_command(update, context):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return

    await update.effective_message.reply_text(
        "🔧 KRIZIS METROSHOP — АДМИН-ПАНЕЛЬ\n\n"
        "/orders — последние заказы\n"
        "/done ID — завершить заказ\n"
        "/cancel ID — отменить заказ\n"
        "/giftpaid ID — подтвердить подарки\n"
        "/stats — статистика"
    )


async def orders_command(update, context):
    if not is_admin(update.effective_user.id):
        return

    orders = get_recent_orders(20)

    if not orders:
        await update.effective_message.reply_text(
            "Заказов пока нет."
        )
        return

    for order in orders:
        await update.effective_message.reply_text(
            f'📦 ЗАКАЗ №{order["id"]}\n\n'
            f'Покупатель: @{order["username"]}\n'
            f'ID: {order["user_id"]}\n'
            f'Товар: {order["product_name"]}\n'
            f'Цена: {order["price"]}⭐\n'
            f'Оплата: {order["payment"]}\n'
            f'Статус: {order["status"]}\n'
            f'Дата: {order["created"]}'
        )


async def finish_order(
    update,
    context,
    new_status,
    allowed_statuses
):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Укажи ID. Например: /done 12"
        )
        return

    try:
        order_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(
            "ID должен быть числом."
        )
        return

    order = get_order(order_id)

    if order is None:
        await update.effective_message.reply_text(
            "Заказ не найден."
        )
        return

    if order["status"] not in allowed_statuses:
        await update.effective_message.reply_text(
            f'Нельзя изменить заказ со статусом: {order["status"]}'
        )
        return

    set_order_status(order_id, new_status)

    await update.effective_message.reply_text(
        f"Заказ №{order_id}: {new_status}."
    )

    if new_status == "Оплачено":
        customer_text = (
            f"🎁 Подарок по заказу №{order_id} подтверждён.\n"
            "Заказ передан в работу."
        )

    elif new_status == "Выполнен":
        customer_text = (
            f"✅ ТВОЙ ЗАКАЗ №{order_id} ВЫПОЛНЕН!\n\n"
            f'Услуга: {order["product_name"]}\n'
            "Спасибо за заказ в KRIZIS METROSHOP!"
        )

    else:
        customer_text = (
            f"❌ Заказ №{order_id} отменён.\n"
            f"По вопросам напиши @{MANAGER}."
        )

    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=customer_text
        )
    except Exception:
        logger.exception("Не удалось уведомить покупателя")


async def done_command(update, context):
    await finish_order(
        update,
        context,
        "Выполнен",
        {"Оплачено"}
    )


async def cancel_command(update, context):
    await finish_order(
        update,
        context,
        "Отменён",
        {
            "Оплачено",
            "Ожидает оплаты",
            "Ожидает подтверждения подарка"
        }
    )


async def giftpaid_command(update, context):
    await finish_order(
        update,
        context,
        "Оплачено",
        {"Ожидает подтверждения подарка"}
    )


async def stats_command(update, context):
    if not is_admin(update.effective_user.id):
        return

    with db_connect() as con:
        total = con.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0]

        paid = con.execute(
            "SELECT COUNT(*) FROM orders "
            "WHERE status IN ('Оплачено', 'Выполнен')"
        ).fetchone()[0]

        completed = con.execute(
            "SELECT COUNT(*) FROM orders "
            "WHERE status = 'Выполнен'"
        ).fetchone()[0]

        cancelled = con.execute(
            "SELECT COUNT(*) FROM orders "
            "WHERE status = 'Отменён'"
        ).fetchone()[0]

    await update.effective_message.reply_text(
        "📊 СТАТИСТИКА KRIZIS\n\n"
        f"Всего заказов: {total}\n"
        f"Оплачено / в работе: {paid}\n"
        f"Выполнено: {completed}\n"
        f"Отменено: {cancelled}"
    )


# =====================================================
# ЗАПУСК
# =====================================================

def main():
    if not TOKEN:
        raise RuntimeError(
            "Не 
