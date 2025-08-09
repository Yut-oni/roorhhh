from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
from telegram import ParseMode
import requests
from bs4 import BeautifulSoup
import os
import tempfile
import re

TOKEN = 'pontuapi'
ID_GRUPO = -1002434065970  # Cambia al ID de tu grupo

PREGUNTA_PALABRA, PREGUNTA_DESCARGA = range(2)

PALABRAS_SALIR = {'salir', 'termino', 'terminar', 'cancelar', 'exit'}
PALABRAS_RETROCEDER = {'retroceder', 'atrás', 'atras'}

def escape_markdown(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def buscar_videos_pagina(palabra_clave, pagina=1):
    base_url = "https://www.xnxx.es/search/"
    palabra_url = palabra_clave.replace(' ', '+')
    if pagina == 1:
        url_busqueda = f"{base_url}{palabra_url}/"
    else:
        url_busqueda = f"{base_url}{palabra_url}/{pagina}"

    resp = requests.get(url_busqueda)
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    videos = soup.find_all('div', class_='thumb-block')
    if not videos:
        return []

    videos_encontrados = []
    for video in videos:
        enlace_relativo = video.find('a', href=True)['href']
        url_video = "https://www.xnxx.es" + enlace_relativo

        img_url = None
        video_pic_div = video.find('div', class_='video-pic')
        if video_pic_div:
            img_tag = video_pic_div.find('img')
            if img_tag:
                img_url = img_tag.get('data-src') or img_tag.get('data-lazy-src') or img_tag.get('src')
        if not img_url:
            img_tag = video.find('img')
            if img_tag:
                img_url = img_tag.get('data-src') or img_tag.get('data-lazy-src') or img_tag.get('src')

        titulo_tag = video.find('p')
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else 'Sin título'

        videos_encontrados.append({
            'titulo': titulo,
            'miniatura': img_url,
            'url_video': url_video
        })
    return videos_encontrados

def descargar_video_temporal(url_pagina):
    resp = requests.get(url_pagina)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    enlace_mp4 = None
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.endswith('.mp4') or '.mp4?' in href:
            enlace_mp4 = href
            break

    if not enlace_mp4:
        raise Exception("No se encontró enlace mp4 en la página.")

    response = requests.get(enlace_mp4, stream=True)
    block_size = 1024

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
    ruta_temp = temp_file.name
    with temp_file as f:
        for chunk in response.iter_content(chunk_size=block_size):
            if chunk:
                f.write(chunk)
    return ruta_temp

def start(update, context):
    update.message.reply_text(
        "Hola! Ingresa la palabra clave para buscar videos.\n"
        "Puedes escribir 'salir' para cancelar en cualquier momento."
    )
    return PREGUNTA_PALABRA

def recibir_palabra(update, context):
    texto = update.message.text.strip().lower()
    if texto in PALABRAS_SALIR:
        update.message.reply_text('Operación cancelada. ¡Hasta luego!')
        return ConversationHandler.END

    context.user_data['palabra'] = update.message.text.strip()
    context.user_data['pagina_actual'] = 1
    context.user_data['videos'] = []
    context.user_data['indice'] = 0

    return cargar_y_mostrar_videos(update, context)

def cargar_y_mostrar_videos(update, context):
    indice = context.user_data['indice']
    videos = context.user_data['videos']
    palabra = context.user_data['palabra']
    pagina = context.user_data['pagina_actual']

    # Si ya mostramos todos los videos de la lista actual, cargamos la siguiente página
    if indice >= len(videos):
        pagina += 1
        context.user_data['pagina_actual'] = pagina
        videos = buscar_videos_pagina(palabra, pagina)
        if not videos:
            update.message.reply_text("No se encontraron más videos. Fin de la búsqueda.")
            return ConversationHandler.END
        context.user_data['videos'] = videos
        context.user_data['indice'] = 0
        indice = 0

    video = videos[indice]
    texto = f"🎬 *Título:* {video['titulo']}\n\n¿Quieres descargar este video? (responde 's' o 'n')\n\nPara salir escribe 'salir' o 'cancelar'."
    texto_escapado = escape_markdown(texto)

    try:
        if video['miniatura']:
            context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=video['miniatura'],
                caption=texto_escapado,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            update.message.reply_text(texto_escapado, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        print(f"Error enviando foto o mensaje: {e}")
        update.message.reply_text(texto)

    return PREGUNTA_DESCARGA

def procesar_respuesta_descarga(update, context):
    texto = update.message.text.strip().lower()
    if texto in PALABRAS_SALIR:
        update.message.reply_text('Operación cancelada. ¡Hasta luego!')
        return ConversationHandler.END

    indice = context.user_data['indice']
    videos = context.user_data['videos']

    if texto == 's':
        video = videos[indice]
        update.message.reply_text(f"Descargando y enviando video: {video['titulo']} ... Esto puede tardar.")

        try:
            ruta_video = descargar_video_temporal(video['url_video'])
            with open(ruta_video, 'rb') as f:
                context.bot.send_video(chat_id=ID_GRUPO, video=f, caption=video['titulo'])
            os.remove(ruta_video)
        except Exception as e:
            update.message.reply_text(f"Error al descargar/enviar video: {e}")
    else:
        update.message.reply_text("Video saltado.")

    context.user_data['indice'] += 1
    return cargar_y_mostrar_videos(update, context)

def cancelar(update, context):
    update.message.reply_text('Operación cancelada. ¡Hasta luego!')
    return ConversationHandler.END

def mensaje_inicio(update, context):
    texto = update.message.text.lower()
    if 'bot' in texto:
        return start(update, context)
    else:
        return  # Ignorar otros mensajes

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text & Filters.regex(r'(?i).*bot.*'), mensaje_inicio)],
        states={
            PREGUNTA_PALABRA: [MessageHandler(Filters.text & ~Filters.command, recibir_palabra)],
            PREGUNTA_DESCARGA: [MessageHandler(Filters.text & ~Filters.command, procesar_respuesta_descarga)],
        },
        fallbacks=[
            CommandHandler('cancel', cancelar),
        ],
        allow_reentry=True,
    )

    dp.add_handler(conv_handler)

    print("Bot iniciado...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
