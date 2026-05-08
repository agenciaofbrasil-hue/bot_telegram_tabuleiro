
import os
import json
import logging
import crcmod
import qrcode
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(
    format=\'%(asctime)s - %(name)s - %(levelname)s - %(message)s\
),
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8691660516:AAHUuDpYknwz5630zrCj7BUro72LJpXxjKQ")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) # Set your admin Telegram ID here

GROUPS_DATA_FILE = "groups_data.json"
BUTTONS_FILE = "buttons.json" # This will be deprecated, buttons will be stored in groups_data.json
PHOTO_URL = os.getenv("PHOTO_URL", "")
PHOTO_FILE = "photo.jpg"
MESSAGE_TEXT = "🔥 O TABULEIRO ESTÁ CHEIO! 🔥\n\n👇 Acesse nossos grupos exclusivos abaixo 👇"

# Admin Pix Configuration
ADMIN_PIX_KEY = "71984498445"
ADMIN_PIX_NAME = "Leandro da Cruz Caldeiras"
ADMIN_PIX_CITY = "Salvador"
LICENSE_PRICE = 19.99
TRIAL_DAYS = 7

# Default Plans (can be overridden per group)
DEFAULT_PLANS = {
    "semanal": {"name": "Semanal", "price": 4.99},
    "mensal": {"name": "Mensal", "price": 9.99},
    "trimestral": {"name": "Trimestral", "price": 29.99},
    "semestral": {"name": "Semestral", "price": 39.99},
    "anual": {"name": "Anual", "price": 49.99},
}

def calculate_crc16(payload):
    crc16 = crcmod.mkCrcFun(0x11021, initCrc=0xFFFF, rev=False, xorOut=0x0000)
    return hex(crc16(payload.encode(\'utf-8\')))[2:].upper().zfill(4)

def generate_pix_payload(value, name, city, pix_key):
    # Payload Format Indicator (00)
    payload = "000201"
    
    # Merchant Account Information (26)
    merchant_account_info = f"0014br.gov.bcb.pix01{len(pix_key):02d}{pix_key}"
    payload += f"26{len(merchant_account_info):02d}{merchant_account_info}"
    
    # Merchant Category Code (52)
    payload += "52040000"
    
    # Transaction Currency (53)
    payload += "5303986"
    
    # Transaction Amount (54)
    amount_str = f"{value:.2f}"
    payload += f"54{len(amount_str):02d}{amount_str}"
    
    # Country Code (58)
    payload += "5802BR"
    
    # Merchant Name (59)
    payload += f"59{len(name):02d}{name}"
    
    # Merchant City (60)
    payload += f"60{len(city):02d}{city}"
    
    # Additional Data Field Template (62)
    additional_data_field = "0503***"
    payload += f"62{len(additional_data_field):02d}{additional_data_field}"
    
    # CRC16 (63)
    payload += "6304"
    payload += calculate_crc16(payload)
    
    return payload

def generate_qr_code_image(payload, file_path):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(file_path)

def load_groups_data():
    try:
        with open(GROUPS_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_groups_data(data):
    with open(GROUPS_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_group_data(chat_id):
    groups_data = load_groups_data()
    return groups_data.get(str(chat_id), {})

def update_group_data(chat_id, key, value):
    groups_data = load_groups_data()
    chat_id_str = str(chat_id)
    if chat_id_str not in groups_data:
        groups_data[chat_id_str] = {
            "license_active": False,
            "license_expiry": None,
            "pix_config": {"key": "", "name": "", "city": ""},
            "buttons": [],
            "plans": DEFAULT_PLANS
        }
    groups_data[chat_id_str][key] = value
    save_groups_data(groups_data)

def load_buttons(chat_id):
    group_data = get_group_data(chat_id)
    return group_data.get("buttons", [])

def save_buttons(chat_id, buttons):
    update_group_data(chat_id, "buttons", buttons)

def build_keyboard(chat_id):
    buttons = load_buttons(chat_id)
    keyboard = []
    for btn in buttons:
        keyboard.append([InlineKeyboardButton(btn["text"], url=btn["url"])])
    return InlineKeyboardMarkup(keyboard)

async def check_license(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_data = get_group_data(chat_id)
    
    if not group_data or not group_data.get("license_active"):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sua licença para usar o bot está inativa ou expirou. Por favor, use o comando /licenca para regularizar."
        )
        return False
    
    expiry_date_str = group_data.get("license_expiry")
    if expiry_date_str:
        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
        if datetime.now().date() > expiry_date:
            update_group_data(chat_id, "license_active", False)
            await context.bot.send_message(
                chat_id=chat_id,
                text="Sua licença expirou. Por favor, use o comando /licenca para regularizar."
            )
            return False
    return True

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.data
    if chat_id:
        group_data = get_group_data(chat_id)
        if not group_data or not group_data.get("license_active"):
            logger.info(f"Não enviando mensagem agendada para o chat {chat_id}: licença inativa.")
            return

        expiry_date_str = group_data.get("license_expiry")
        if expiry_date_str:
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            if datetime.now().date() > expiry_date:
                update_group_data(chat_id, "license_active", False)
                logger.info(f"Não enviando mensagem agendada para o chat {chat_id}: licença expirada.")
                return

        try:
            reply_markup = build_keyboard(chat_id)
            if PHOTO_URL:
                await context.bot.send_photo(chat_id=chat_id, photo=PHOTO_URL, caption=MESSAGE_TEXT, reply_markup=reply_markup)
            elif os.path.exists(PHOTO_FILE):
                with open(PHOTO_FILE, "rb") as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=MESSAGE_TEXT, reply_markup=reply_markup)
            else:
                await context.bot.send_message(chat_id=chat_id, text=MESSAGE_TEXT, reply_markup=reply_markup)
            logger.info(f"Mensagem agendada enviada para o chat {chat_id}.")
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem para o chat {chat_id}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        chat_id = str(update.effective_chat.id)
        user_id = update.effective_user.id

        groups_data = load_groups_data()
        if chat_id not in groups_data:
            # New group, start trial
            expiry_date = datetime.now().date() + timedelta(days=TRIAL_DAYS)
            groups_data[chat_id] = {
                "license_active": True,
                "license_expiry": expiry_date.strftime("%Y-%m-%d"),
                "pix_config": {"key": "", "name": "", "city": ""},
                "buttons": [],
                "plans": DEFAULT_PLANS
            }
            save_groups_data(groups_data)
            await update.message.reply_text(
                f"Bem-vindo! Você tem {TRIAL_DAYS} dias de teste grátis. "
                "Use /config_pix para configurar sua chave Pix e /assinar para ver os planos."
            )
        
        context.bot_data["chat_id"] = chat_id # For backward compatibility with existing scheduled messages
        await update.message.reply_text(
            f"✅ Bot ativado! Chat ID: {chat_id}\n\n"
            "📋 Comandos disponíveis:\n"
            "/add Nome|link - Adicionar botão\n"
            "/remove Nome - Remover botão\n"
            "/list - Ver botões atuais\n"
            "/send - Enviar mensagem agora\n"
            "/assinar - Ver planos de assinatura\n"
            "/config_pix chave|nome|cidade - Configurar sua chave Pix\n"
            "/licenca - Pagar a licença do bot\n\n"
            "As mensagens serão enviadas a cada 1 hora."
        )
        current_jobs = context.job_queue.get_jobs_by_name(f\'hourly_message_{chat_id}\'
)
        for job in current_jobs:
            job.schedule_removal()
        context.job_queue.run_repeating(send_scheduled_message, interval=3600, first=5, data=chat_id, name=f\'hourly_message_{chat_id}\'
)

async def add_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_license(update, context): return
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("❌ Uso: /add Nome do Botão|https://link.com")
        return
    text = " ".join(context.args)
    if "|" not in text:
        await update.message.reply_text("❌ Formato correto: /add Nome do Botão|https://link.com")
        return
    parts = text.split("|", 1)
    button_text = parts[0].strip()
    button_url = parts[1].strip()
    if not button_url.startswith("http"):
        await update.message.reply_text("❌ O link deve começar com http:// ou https://")
        return
    buttons = load_buttons(chat_id)
    buttons.append({"text": button_text, "url": button_url})
    save_buttons(chat_id, buttons)
    await update.message.reply_text(f"✅ Botão adicionado: {button_text}\n🔗 {button_url}")

async def remove_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_license(update, context): return
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("❌ Uso: /remove Nome do Botão")
        return
    button_name = " ".join(context.args).strip()
    buttons = load_buttons(chat_id)
    new_buttons = [btn for btn in buttons if btn["text"].lower() != button_name.lower()]
    if len(new_buttons) == len(buttons):
        await update.message.reply_text(f"❌ Botão \'{button_name}\' não encontrado.")
        return
    save_buttons(chat_id, new_buttons)
    await update.message.reply_text(f"✅ Botão \'{button_name}\' removido!")

async def list_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_license(update, context): return
    chat_id = update.effective_chat.id
    buttons = load_buttons(chat_id)
    if not buttons:
        await update.message.reply_text("📋 Nenhum botão configurado.")
        return
    text = "📋 Botões configurados:\n\n"
    for i, btn in enumerate(buttons, 1):
        text += f"{i}. {btn[\'text\']} → {btn[\'url\]}\n"
    await update.message.reply_text(text)

async def send_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_license(update, context): return
    chat_id = str(update.effective_chat.id)
    try:
        reply_markup = build_keyboard(chat_id)
        if PHOTO_URL:
            await context.bot.send_photo(chat_id=chat_id, photo=PHOTO_URL, caption=MESSAGE_TEXT, reply_markup=reply_markup)
        elif os.path.exists(PHOTO_FILE):
            with open(PHOTO_FILE, "rb") as photo:
                await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=MESSAGE_TEXT, reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=chat_id, text=MESSAGE_TEXT, reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao enviar: {e}")

async def assinar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_license(update, context): return
    chat_id = update.effective_chat.id
    group_data = get_group_data(chat_id)
    plans = group_data.get("plans", DEFAULT_PLANS)

    keyboard = []
    for plan_key, plan_info in plans.items():
        keyboard.append([InlineKeyboardButton(f"{plan_info[\"name\"]}: R${plan_info[\"price\"]:.2f}", callback_data=f"plan_{plan_key}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Escolha um plano de assinatura:",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    if not await check_license(update, context): return

    data = query.data
    if data.startswith("plan_"):
        plan_key = data.split("_")[1]
        group_data = get_group_data(chat_id)
        plans = group_data.get("plans", DEFAULT_PLANS)

        if plan_key in plans:
            plan = plans[plan_key]
            value = plan["price"]
            
            pix_config = group_data.get("pix_config", {})
            pix_key = pix_config.get("key")
            pix_name = pix_config.get("name")
            pix_city = pix_config.get("city")

            if not (pix_key and pix_name and pix_city):
                await query.message.reply_text(
                    "Por favor, configure sua chave Pix, nome e cidade usando /config_pix antes de gerar um QR Code de assinatura."
                )
                return

            payload = generate_pix_payload(value, pix_name, pix_city, pix_key)
            
            qr_code_path = f"qrcode_{chat_id}_{plan_key}.png"
            generate_qr_code_image(payload, qr_code_path)
            
            message = (
                f"Você escolheu o plano {plan[\'name\']} no valor de R${value:.2f}.\n\n"
                f"Para pagar, escaneie o QR Code abaixo ou copie o código Pix Copia e Cola:\n\n"
                f"`{payload}`\n\n"
                f"Após o pagamento, envie o comprovante para o administrador do grupo."
            )
            
            with open(qr_code_path, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=message,
                    parse_mode="Markdown"
                )
            
            if os.path.exists(qr_code_path):
                os.remove(qr_code_path)

async def config_pix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_license(update, context): return
    chat_id = update.effective_chat.id
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("❌ Uso: /config_pix chave_pix|nome_recebedor|cidade")
        return
    
    config_str = " ".join(context.args)
    parts = config_str.split("|")
    if len(parts) != 3:
        await update.message.reply_text("❌ Formato incorreto. Uso: /config_pix chave_pix|nome_recebedor|cidade")
        return
    
    pix_key = parts[0].strip()
    pix_name = parts[1].strip()
    pix_city = parts[2].strip()

    groups_data = load_groups_data()
    chat_id_str = str(chat_id)
    if chat_id_str not in groups_data:
        # This should ideally not happen if /start is always called first
        await update.message.reply_text("Por favor, inicie o bot com /start primeiro.")
        return

    groups_data[chat_id_str]["pix_config"] = {"key": pix_key, "name": pix_name, "city": pix_city}
    save_groups_data(groups_data)
    await update.message.reply_text("✅ Configurações Pix atualizadas para este grupo.")

async def licenca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    group_data = get_group_data(chat_id)

    license_status_message = ""
    if group_data:
        expiry_date_str = group_data.get("license_expiry")
        if expiry_date_str:
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            if group_data.get("license_active") and datetime.now().date() <= expiry_date:
                license_status_message = f"Sua licença está ativa até {expiry_date.strftime("%d/%m/%Y")}.\n"
            else:
                license_status_message = f"Sua licença expirou em {expiry_date.strftime("%d/%m/%Y")}.\n"
        else:
            license_status_message = "Sua licença ainda não foi ativada ou está em período de teste.\n"
    else:
        license_status_message = "Este grupo não está registrado. Por favor, use /start para iniciar o período de teste.\n"

    payload = generate_pix_payload(LICENSE_PRICE, ADMIN_PIX_NAME, ADMIN_PIX_CITY, ADMIN_PIX_KEY)
    qr_code_path = f"qrcode_licenca_{chat_id}.png"
    generate_qr_code_image(payload, qr_code_path)

    message = (
        f"{license_status_message}"
        f"Para ativar ou renovar a licença do bot (R${LICENSE_PRICE:.2f}/mês), "
        f"escaneie o QR Code abaixo ou copie o código Pix Copia e Cola:\n\n"
        f"`{payload}`\n\n"
        f"Após o pagamento, o administrador do bot ativará sua licença."
    )

    with open(qr_code_path, "rb") as photo:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=message,
            parse_mode="Markdown"
        )
    
    if os.path.exists(qr_code_path):
        os.remove(qr_code_path)

# Admin Commands
async def admin_grupos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Acesso negado.")
        return
    
    groups_data = load_groups_data()
    if not groups_data:
        await update.message.reply_text("Nenhum grupo registrado.")
        return
    
    message = "Grupos Registrados:\n\n"
    for chat_id, data in groups_data.items():
        status = "Ativa" if data.get("license_active") else "Inativa"
        expiry = data.get("license_expiry", "N/A")
        message += f"ID: {chat_id}, Status: {status}, Expira em: {expiry}\n"
    await update.message.reply_text(message)

async def admin_ativar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Acesso negado.")
        return
    
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("❌ Uso: /admin_ativar <chat_id>")
        return
    
    target_chat_id = context.args[0]
    groups_data = load_groups_data()
    if target_chat_id not in groups_data:
        await update.message.reply_text(f"Grupo {target_chat_id} não encontrado.")
        return
    
    expiry_date = datetime.now().date() + timedelta(days=30)
    groups_data[target_chat_id]["license_active"] = True
    groups_data[target_chat_id]["license_expiry"] = expiry_date.strftime("%Y-%m-%d")
    save_groups_data(groups_data)
    await update.message.reply_text(f"✅ Licença do grupo {target_chat_id} ativada até {expiry_date.strftime("%d/%m/%Y")}.")

async def admin_desativar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Acesso negado.")
        return
    
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("❌ Uso: /admin_desativar <chat_id>")
        return
    
    target_chat_id = context.args[0]
    groups_data = load_groups_data()
    if target_chat_id not in groups_data:
        await update.message.reply_text(f"Grupo {target_chat_id} não encontrado.")
        return
    
    groups_data[target_chat_id]["license_active"] = False
    save_groups_data(groups_data)
    await update.message.reply_text(f"✅ Licença do grupo {target_chat_id} desativada.")

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_button))
    application.add_handler(CommandHandler("remove", remove_button))
    application.add_handler(CommandHandler("list", list_buttons))
    application.add_handler(CommandHandler("send", send_now))
    application.add_handler(CommandHandler("assinar", assinar))
    application.add_handler(CommandHandler("config_pix", config_pix))
    application.add_handler(CommandHandler("licenca", licenca))
    application.add_handler(CommandHandler("admin_grupos", admin_grupos))
    application.add_handler(CommandHandler("admin_ativar", admin_ativar))
    application.add_handler(CommandHandler("admin_desativar", admin_desativar))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    initial_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if initial_chat_id:
        application.job_queue.run_repeating(send_scheduled_message, interval=3600, first=10, data=initial_chat_id, name=f\'hourly_message_{initial_chat_id}\'
)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == \'__main__\':
    main()
