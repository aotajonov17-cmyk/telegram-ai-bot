import telebot
from telebot import types
from google import genai
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from pptx import Presentation
from pptx.util import Inches, Pt as PptPt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
import os
import sqlite3
import threading

# ==========================================
# SOZLAMALAR 
# ==========================================
TELEGRAM_TOKEN = "9027126170:AAF3N14mENM3HXsM4Zdz9Z9A7UalsmG3ft4"
GEMINI_API_KEY = "AQ.Ab8RN6JFGhlqkpR28jcLHwVplFwv-_FtT1L_O0Egn8GatxBZ2A"

ADMIN_ID = 7920869737  
KARTA_RAQAM = "9860 1606 3950 6767" 
VIP_NARXI = "15 000 so'm"
# ==========================================

client = genai.Client(api_key=GEMINI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

user_temp_data = {}

# --- MA'LUMOTLAR BAZASI ---
conn = sqlite3.connect('mijozlar.db', check_same_thread=False)
db_lock = threading.RLock()
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, username TEXT, referat_count INTEGER DEFAULT 0, slayd_count INTEGER DEFAULT 0, is_vip INTEGER DEFAULT 0)''')
conn.commit()

# Suhbat xotirasi: foydalanuvchining oxirgi xabarlarini SQLite'da saqlash
with db_lock:
    db_cursor = conn.cursor()
    db_cursor.execute('''CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()

def check_user(user_id, username):
    with db_lock:
        db_cursor = conn.cursor()
        db_cursor.execute("SELECT referat_count, slayd_count, is_vip FROM users WHERE user_id=?", (user_id,))
        row = db_cursor.fetchone()
        if not row:
            db_cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
            conn.commit()
            return (0, 0, 0)
        return row

def update_usage(user_id, column):
    # Faqat ruxsat etilgan ustun nomlari
    if column not in ("referat_count", "slayd_count"):
        raise ValueError("Noto'g'ri ustun nomi")
    with db_lock:
        db_cursor = conn.cursor()
        db_cursor.execute(f"UPDATE users SET {column} = {column} + 1 WHERE user_id=?", (user_id,))
        conn.commit()

# --- MENYULAR ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("📄 Referat tayyorlash")
    btn2 = types.KeyboardButton("📊 Slayd tayyorlash")
    markup.add(btn1, btn2)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    username = message.from_user.username or "Ism_yoq"
    _, _, is_vip = check_user(user_id, username)
    status = "💎 VIP (Cheksiz)" if is_vip == 1 else "🎁 Bepul (2 ta urinish)"
    
    text = (
        f"🤖 Salom, {message.from_user.first_name}!\n\n"
        f"Sizning joriy holatingiz: *{status}*\n\n"
        "Men universitet shablonidagi akademik referat va vizual dizaynli professional slaydlar tayyorlaydigan botiman!"
    )
    bot.send_message(user_id, text, reply_markup=main_menu(), parse_mode="Markdown")

@bot.message_handler(commands=['stat'])
def show_stats(message):
    if message.chat.id != ADMIN_ID:
        return
    with db_lock:
        db_cursor = conn.cursor()
        db_cursor.execute("SELECT COUNT(*), SUM(referat_count), SUM(slayd_count), SUM(is_vip) FROM users")
        users, refs, slays, vips = db_cursor.fetchone()
    text = (
        "📊 *BOT STATISTIKASI:*\n\n"
        f"👥 Jami mijozlar: {users} ta\n"
        f"💎 VIP obunachilar: {vips if vips else 0} ta\n"
        f"📄 Yasalgan referatlar: {refs if refs else 0} ta\n"
        f"📊 Yasalgan slaydlar: {slays if slays else 0} ta"
    )
    bot.send_message(ADMIN_ID, text, parse_mode="Markdown")

def ask_payment(user_id):
    text = (
        "🛑 *Sizning bepul limitingiz tugadi!*\n\n"
        f"Botdan cheksiz foydalanish uchun VIP obuna narxi: *{VIP_NARXI}*\n\n"
        f"💳 To'lov uchun karta: `{KARTA_RAQAM}`\n\n"
        "📥 *To'lovni amalga oshirgach, chek rasmini shu yerga botga jo'nating.*"
    )
    bot.send_message(user_id, text, parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.chat.id
    _, _, is_vip = check_user(user_id, "")
    if is_vip == 1:
        bot.reply_to(message, "Siz allaqachon VIP mijozsiz!")
        return
    bot.reply_to(message, "⏳ Chek Adminga yuborildi. Tasdiqlanishini kuting...")
    
    markup = types.InlineKeyboardMarkup()
    btn_yes = types.InlineKeyboardButton("✅ Tasdiqlash (VIP berish)", callback_data=f"app_{user_id}")
    btn_no = types.InlineKeyboardButton("❌ Rad etish", callback_data=f"rej_{user_id}")
    markup.add(btn_yes, btn_no)
    
    file_info = message.photo[-1].file_id
    caption = f"💰 **YANGI TO'LOV CHEKI!**\n\nMijoz ID: {user_id}\nUsername: @{message.from_user.username}"
    bot.send_photo(ADMIN_ID, file_info, caption=caption, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('app_') or call.data.startswith('rej_'))
def handle_admin_decision(call):
    action = call.data.split('_')[0]
    target_user_id = int(call.data.split('_')[1])
    if action == "app":
        with db_lock:
            db_cursor = conn.cursor()
            db_cursor.execute("UPDATE users SET is_vip = 1 WHERE user_id=?", (target_user_id,))
            conn.commit()
        bot.edit_message_caption(caption="✅ CHEK TASDIQLANDI VA VIP BERILDI!", chat_id=call.message.chat.id, message_id=call.message.message_id)
        try:
            bot.send_message(target_user_id, "🎉 Tabriklaymiz! To'lovingiz tasdiqlandi va sizga VIP status berildi!", parse_mode="Markdown")
        except:
            pass
    elif action == "rej":
        bot.edit_message_caption(caption="❌ CHEK RAD ETILDI!", chat_id=call.message.chat.id, message_id=call.message.message_id)
        try:
            bot.send_message(target_user_id, "❌ Uzur, chekingiz tasdiqlanmadi.")
        except:
            pass

# --- REFERAT TAYYORLASH ---
@bot.message_handler(func=lambda message: message.text == "📄 Referat tayyorlash")
def ask_referat(message):
    user_id = message.chat.id
    ref_count, _, is_vip = check_user(user_id, message.from_user.username)
    if is_vip == 0 and ref_count >= 2:
        ask_payment(user_id)
        return
    msg = bot.reply_to(message, "✍️ Referat uchun **mavzuni** yozib yuboring:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, get_referat_topic)

def get_referat_topic(message):
    mavzu = message.text
    user_id = message.chat.id
    if mavzu in ["📄 Referat tayyorlash", "📊 Slayd tayyorlash", "/start"]:
        bot.send_message(user_id, "Bekor qilindi.", reply_markup=main_menu())
        return
    
    user_temp_data[user_id] = {'mavzu': mavzu}

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton("📘 O'rta (5-7 sahifa)", callback_data="ref_orta")
    btn2 = types.InlineKeyboardButton("📚 Katta (10-12 sahifa)", callback_data="ref_katta")
    markup.add(btn1, btn2)

    bot.send_message(user_id, f"📌 Mavzu: *{mavzu}*\n\nReferat hajmini tanlang:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ref_'))
def process_referat_generation(call):
    user_id = call.message.chat.id
    
    if user_id not in user_temp_data:
        bot.answer_callback_query(call.id, "Xatolik yuz berdi.")
        return

    mavzu = user_temp_data[user_id]['mavzu']
    bot.answer_callback_query(call.id, "Referat yozilmoqda...")
    bot.edit_message_text(chat_id=user_id, message_id=call.message.message_id, text=f"⏳ *'{mavzu}'* bo'yicha universitet shablonidagi referat tayyorlanmoqda...", parse_mode="Markdown")

    try:
        prompt = (
            f"O'zbekiston Milliy Universiteti Jizzax filiali talablari asosida '{mavzu}' mavzusida akademik referat yoz. "
            "Referat quyidagi tuzilmada bo'lsin: "
            "1. REJA (Kirish, kamida 8-10 ta asosiy band, Xulosa va takliflar, Foydalanilgan adabiyotlar). "
            "2. KIRISH (Dolzarbligi, maqsadi va vazifalari). "
            "3. ASOSIY QISM (Rejadagi bandlar bo'yicha batafsil ilmiy matn va tahlillar). "
            "4. XULOSA VA TAKLIFLAR. "
            "5. FOYDALANILGAN ADABIYOTLAR."
        )
        
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
        )
        matn = response.text

        bot.send_message(user_id, "📝 Word hujjati rasmiylashtirilmoqda (Times New Roman 14, 1.5 interval, 3-2-2-1.5 hoshiya)...")

        doc = Document()

        for section in doc.sections:
            section.top_margin = Cm(2)
            section.bottom_margin = Cm(2)
            section.left_margin = Cm(3)
            section.right_margin = Cm(1.5)

        style = doc.styles['Normal']
        font = style.font
        font.name = 'Times New Roman'
        font.size = Pt(14)

        # Titul sahifasi
        p_header = doc.add_paragraph()
        p_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_h = p_header.add_run("OʻZBEKISTON RESPUBLIKASI OLIY TA'LIM, FAN VA INNOVATSIYALAR VAZIRLIGI\nMIRZO ULUG'BEK NOMIDAGI O`ZBEKISTON MILLIY UNIVERSITETI JIZZAX FILIALI\n")
        r_h.bold = True
        r_h.font.size = Pt(12)

        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_title.paragraph_format.space_before = Pt(30)
        p_title.paragraph_format.space_after = Pt(30)
        r_t = p_title.add_run(f"REFERAT\n\nMavzu: {mavzu.upper()}")
        r_t.bold = True
        r_t.font.size = Pt(15)

        p_info = doc.add_paragraph()
        p_info.paragraph_format.space_before = Pt(50)
        p_info.paragraph_format.left_indent = Cm(8)
        r_i = p_info.add_run("Bajardi: ... guruh talabasi\nQabul qildi: ...")
        r_i.font.size = Pt(14)

        p_foot = doc.add_paragraph()
        p_foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_foot.paragraph_format.space_before = Pt(80)
        r_f = p_foot.add_run("Jizzax — 2026")
        r_f.bold = True
        r_f.font.size = Pt(14)

        doc.add_page_break()

        paragraphs = matn.split('\n')
        for p_text in paragraphs:
            if p_text.strip():
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                p.paragraph_format.line_spacing = 1.5
                p.paragraph_format.first_line_indent = Cm(1.25)
                
                run = p.add_run(p_text.strip())
                run.font.name = 'Times New Roman'
                run.font.size = Pt(14)

        fayl_nomi = f"{mavzu[:20].replace(' ', '_')}.docx"
        doc.save(fayl_nomi)

        with open(fayl_nomi, 'rb') as f:
            bot.send_document(user_id, f, caption="✅ Universitet shablonidagi referatingiz tayyor!", reply_markup=main_menu())
        os.remove(fayl_nomi)
        update_usage(user_id, 'referat_count')
    except Exception as e:
        bot.send_message(user_id, f"❌ Xato: {e}", reply_markup=main_menu())

# --- SLAYD TAYYORLASH (VIZUAL DIZAYNLI SHABLON) ---
@bot.message_handler(func=lambda message: message.text == "📊 Slayd tayyorlash")
def ask_slayd(message):
    user_id = message.chat.id
    _, slayd_count, is_vip = check_user(user_id, message.from_user.username)
    if is_vip == 0 and slayd_count >= 2:
        ask_payment(user_id)
        return
    msg = bot.reply_to(message, "✍️ Slayd uchun **mavzuni** yozib yuboring:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, get_slayd_topic)

def get_slayd_topic(message):
    mavzu = message.text
    user_id = message.chat.id
    if mavzu in ["📄 Referat tayyorlash", "📊 Slayd tayyorlash", "/start"]:
        bot.send_message(user_id, "Bekor qilindi.", reply_markup=main_menu())
        return
    
    user_temp_data[user_id] = {'mavzu': mavzu}

    markup = types.InlineKeyboardMarkup(row_width=3)
    btn10 = types.InlineKeyboardButton("10 ta slayd", callback_data="slide_10")
    btn15 = types.InlineKeyboardButton("15 ta slayd", callback_data="slide_15")
    btn20 = types.InlineKeyboardButton("20 ta slayd", callback_data="slide_20")
    markup.add(btn10, btn15, btn20)

    bot.send_message(user_id, f"📌 Mavzu: *{mavzu}*\n\nNechta slayddan iborat bo'lsin?", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('slide_'))
def process_slide_count(call):
    user_id = call.message.chat.id
    count = call.data.split('_')[1]
    
    if user_id not in user_temp_data:
        bot.answer_callback_query(call.id, "Xatolik yuz berdi.")
        return

    mavzu = user_temp_data[user_id]['mavzu']
    bot.answer_callback_query(call.id, f"{count} ta slayd tanlandi!")
    bot.edit_message_text(chat_id=user_id, message_id=call.message.message_id, text=f"⏳ *'{mavzu}'* bo'yicha vizual dizaynli {count} ta professional slayd tayyorlanmoqda...", parse_mode="Markdown")

    try:
        prompt = (
            f"O'zbek tilida '{mavzu}' mavzusida chuqur tahliliy, akademik va boyitilgan ma'lumotlarga ega aniq {count} ta slayddan iborat taqdimot matnini yoz. "
            "Har bir slaydni aniq 'SLAYD:' so'zi bilan boshlab ajratib yoz. "
            "1-qator sarlavha, qolgan qatorlar esa batafsil ma'lumot beruvchi bullet-point bandlar bo'lsin."
        )
        
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
        )
        matn = response.text

        bot.send_message(user_id, "📊 Prezentatsiya vizual dizayni (.pptx) shakllantirilmoqda...")

        prs = Presentation()
        
        # 1-Slayd: Titul sahifasi (Maxsus ko'k fon dizayni)
        slide_layout = prs.slide_layouts[6] # Bo'sh slayd
        slide = prs.slides.add_slide(slide_layout)
        
        # Orqa fon rangi (To'q ko'k)
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(16, 37, 66)

        # Sarlavha matni
        txBox = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(11), Inches(2))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = mavzu
        p.font.name = 'Arial'
        p.font.size = PptPt(36)
        p.font.bold = True
        p.font.color.rgb = RGBColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER

        # Tagiga ma'lumot
        txBox_sub = slide.shapes.add_textbox(Inches(1), Inches(4.5), Inches(11), Inches(1))
        tf_sub = txBox_sub.text_frame
        p_sub = tf_sub.paragraphs[0]
        p_sub.text = "Taqdimot / Ma'ruza\nO'zbekiston Respublikasi — 2026"
        p_sub.font.name = 'Arial'
        p_sub.font.size = PptPt(18)
        p_sub.font.color.rgb = RGBColor(200, 220, 240)
        p_sub.alignment = PP_ALIGN.CENTER

        slaydlar = matn.split('SLAYD:')[1:]

        for slayd_matni in slaydlar:
            qatorlar = [q.strip() for q in slayd_matni.strip().split('\n') if q.strip()]
            if len(qatorlar) > 0:
                sarlavha = qatorlar[0].replace('*', '').replace('#', '').strip()
                asosiy_qism = '\n'.join(qatorlar[1:]).replace('*', '').replace('#', '').strip()

                slide = prs.slides.add_slide(prs.slide_layouts[6])
                
                # Yuqori sarlavha paneli (Header box)
                header_box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.3), Inches(1.1))
                header_box.fill.solid()
                header_box.fill.fore_color.rgb = RGBColor(16, 37, 66)
                header_box.line.color.rgb = RGBColor(16, 37, 66)
                
                tf_h = header_box.text_frame
                tf_h.word_wrap = True
                p_h = tf_h.paragraphs[0]
                p_h.text = sarlavha
                p_h.font.name = 'Arial'
                p_h.font.size = PptPt(24)
                p_h.font.bold = True
                p_h.font.color.rgb = RGBColor(255, 255, 255)
                p_h.alignment = PP_ALIGN.LEFT

                # Matn bloki
                content_box = slide.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(11.7), Inches(5))
                tf_c = content_box.text_frame
                tf_c.word_wrap = True
                
                lines = asosiy_qism.split('\n')
                for i, line in enumerate(lines):
                    if i == 0:
                        p_c = tf_c.paragraphs[0]
                    else:
                        p_c = tf_c.add_paragraph()
                    
                    p_c.text = "• " + line.replace("- ", "").replace("* ", "")
                    p_c.font.name = 'Arial'
                    p_c.font.size = PptPt(16)
                    p_c.font.color.rgb = RGBColor(40, 40, 40)
                    p_c.space_after = PptPt(10)

        fayl_nomi = f"{mavzu[:20].replace(' ', '_')}.pptx"
        prs.save(fayl_nomi)

        with open(fayl_nomi, 'rb') as f:
            bot.send_document(user_id, f, caption=f"💎 Marhamat, vizual dizaynli va boyitilgan {count} ta slayddan iborat taqdimotingiz tayyor!", reply_markup=main_menu())
        os.remove(fayl_nomi)
        update_usage(user_id, 'slayd_count')
    except Exception as e:
        bot.send_message(user_id, f"❌ Xato: {e}", reply_markup=main_menu())

# --- GEMINI BILAN SUHBAT VA XOTIRA ---
@bot.message_handler(func=lambda message: bool(message.text) and message.text not in ["📄 Referat tayyorlash", "📊 Slayd tayyorlash"] and not message.text.startswith('/'))
def handle_chat_with_memory(message):
    user_id = message.chat.id
    user_text = message.text.strip()
    if not user_text:
        return

    try:
        # Xabarlar bazadan olinadi; har bir amal uchun alohida cursor ishlatiladi.
        with db_lock:
            db_cursor = conn.cursor()
            db_cursor.execute(
                "SELECT role, content FROM chat_history WHERE user_id=? ORDER BY id DESC LIMIT 12",
                (user_id,)
            )
            history = list(reversed(db_cursor.fetchall()))
            db_cursor.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, "user", user_text)
            )
            conn.commit()

        prompt_parts = [
            "Sen o'zbek tilida javob beradigan foydali Telegram yordamchisisan. "
            "Oldingi suhbatni hisobga ol, lekin bilmagan narsangni to'qib chiqarmagin."
        ]
        for role, content in history:
            label = "Foydalanuvchi" if role == "user" else "Yordamchi"
            prompt_parts.append(f"{label}: {content}")
        prompt_parts.append(f"Foydalanuvchi: {user_text}")
        prompt_parts.append("Yordamchi:")

        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents="\n\n".join(prompt_parts),
        )
        answer = (response.text or "Kechirasiz, hozir javob tayyorlay olmadim.").strip()

        with db_lock:
            db_cursor = conn.cursor()
            db_cursor.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, "assistant", answer)
            )
            # Har bir foydalanuvchi uchun oxirgi 100 ta yozuvni qoldiramiz.
            db_cursor.execute(
                "DELETE FROM chat_history WHERE user_id=? AND id NOT IN "
                "(SELECT id FROM chat_history WHERE user_id=? ORDER BY id DESC LIMIT 100)",
                (user_id, user_id)
            )
            conn.commit()

        # Telegram xabar uzunligi chegarasiga moslab yuborish.
        for start in range(0, len(answer), 4000):
            bot.send_message(user_id, answer[start:start + 4000], reply_markup=main_menu())
    except Exception as e:
        print(f"Suhbat xatosi: {e}")
        bot.send_message(user_id, f"❌ Hozir javob berishda xato yuz berdi: {e}", reply_markup=main_menu())

print("Vizual dizaynli slayd, referat va suhbat xotirasi boti ishga tushdi!")
bot.infinity_polling()