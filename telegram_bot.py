
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import time as dt_time

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Token do bot (substitua pelo seu token real ou use variável de ambiente)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8722322067:AAHrqv1lhpvw-aXkZZR66PzK3siaZ7o-Mxo")

# Mensagem e botões inline
MESSAGE_TEXT = "🔥 Acesse nossos grupos exclusivos!"
KEYBOARD = [
    [InlineKeyboardButton("Prévias da Nay", url="https://t.me/nattysafada")]
]
REPLY_MARKUP = InlineKeyboardMarkup(KEYBOARD)

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia a mensagem agendada para o chat_id configurado."""
    chat_id = context.job.data # O chat_id é passado como data para o job
    if chat_id:
        try:
            await context.bot.send_message(chat_id=chat_id, text=MESSAGE_TEXT, reply_markup=REPLY_MARKUP)
            logger.info(f"Mensagem agendada enviada para o chat {chat_id}.")
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem agendada para o chat {chat_id}: {e}")
    else:
        logger.warning("CHAT_ID não configurado para o job.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem de boas-vindas, armazena o chat_id e agenda a tarefa."""
    if update.effective_chat:
        chat_id = str(update.effective_chat.id)
        logger.info(f"Chat ID capturado: {chat_id}")

        # Armazena o chat_id no contexto do bot para uso posterior
        context.bot_data['chat_id'] = chat_id

        await update.message.reply_text(
            f"Olá! Eu sou o bot de agendamento. O Chat ID deste grupo é {chat_id}. "
            "Começarei a enviar mensagens agendadas aqui. "
            "Você pode definir o TELEGRAM_CHAT_ID como uma variável de ambiente para persistência."
        )

        # Remove jobs antigos para este chat_id, se existirem
        current_jobs = context.job_queue.get_jobs_by_name(f'hourly_message_{chat_id}')
        for job in current_jobs:
            job.schedule_removal()

        # Agenda a tarefa para enviar a mensagem a cada hora
        context.job_queue.run_repeating(
            send_scheduled_message, 
            interval=3600, # 1 hora em segundos
            first=0, # Envia a primeira mensagem imediatamente
            data=chat_id, 
            name=f'hourly_message_{chat_id}'
        )
        logger.info(f"Tarefa agendada para o chat {chat_id}.")

    else:
        logger.warning("Não foi possível obter o effective_chat para o comando /start.")

def main() -> None:
    """Inicia o bot e o agendador."""
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    # Tenta carregar o CHAT_ID da variável de ambiente ao iniciar
    initial_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if initial_chat_id:
        logger.info(f"CHAT_ID carregado da variável de ambiente: {initial_chat_id}")
        # Agenda a tarefa para o chat_id inicial
        application.job_queue.run_repeating(
            send_scheduled_message, 
            interval=3600, 
            first=0, 
            data=initial_chat_id, 
            name=f'hourly_message_{initial_chat_id}'
        )
        logger.info(f"Tarefa agendada para o chat {initial_chat_id} ao iniciar.")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
