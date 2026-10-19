"""Editable public copy, grouped by where it appears on a registration page."""

# key, admin label, default, required, multiline
COPY_GROUPS = [
    ("6. Шапка и подвал страницы", "Название, подписи и флаг. Необязательную надпись можно скрыть, оставив поле пустым.", [
        ("brand_name", "Название в шапке", "DISCO UKRAÏNA", False, False),
        ("show_flag", "Показывать флаг Украины в шапке", True, False, False),
        ("header_tagline", "Подпись в шапке", "МУЗИКА. СПІЛЬНОТА. СВОЇ.", False, False),
        ("jump_label", "Ссылка перехода к форме", "До форми", False, False),
        ("footer_brand", "Название в подвале", "DISCO UKRAÏNA", False, False),
        ("footer_tagline", "Подпись в подвале", "Об’єднані музикою. Натхненні Україною.", False, False),
    ]),
    ("7. Надписи рядом с афишей и мероприятием", "Дополнительные надписи вокруг уже настроенного описания события. Изменения не меняют текст, нарисованный внутри самой афиши.", [
        ("poster_caption", "Подпись под афишей", "ТРОХИ МАГІЇ. БАГАТО МУЗИКИ.", False, False),
        ("poster_alt", "Описание афиши для доступности", "Афіша події", True, False),
        ("poster_open_label", "Описание ссылки открытия афиши", "Відкрити афішу у повному розмірі", True, False),
        ("universal_headline", "Крупный текст универсального оформления", "ОБ’ЄДНАНІ\nМУЗИКОЮ.", False, True),
        ("universal_subtitle", "Подпись универсального оформления", "НАТХНЕННІ УКРАЇНОЮ.", False, False),
        ("eyebrow", "Надпись над главным заголовком", "ЗУСТРІНЕМОСЯ НА ТАНЦПОЛІ", False, False),
        ("date_label", "Подпись к дате события", "КОЛИ", False, False),
        ("venue_label", "Подпись к месту события", "ДЕ", False, False),
        ("timezone_label", "Подпись часового пояса", "час Ізраїлю", False, False),
        ("details_label", "Кнопка раскрытия подробностей", "Програма, костюми та корисні деталі", True, False),
        ("event_link_label", "Ссылка на подробности о событии", "Докладніше про подію", True, False),
    ]),
    ("8. Форма и кнопка отправки", "Все подписи формы. Обязательные поля здесь — это названия кнопок и полей, которые нужны участнику для заполнения.", [
        ("form_eyebrow", "Маленькая надпись над формой", "ЛИШЕ ЧОТИРИ ПОЛЯ", False, False),
        ("form_title", "Заголовок формы", "Залиште свої контакти", True, False),
        ("form_hint", "Пояснение под заголовком формы", "Щоб організатори могли опрацювати Вашу заявку.", False, True),
        ("first_name_label", "Поле имени", "Ім’я", True, False),
        ("last_name_label", "Поле фамилии", "Прізвище", True, False),
        ("phone_label", "Поле телефона", "Телефон", True, False),
        ("email_label", "Поле email", "Email", True, False),
        ("phone_placeholder", "Пример внутри поля телефона", "+972 50 234 5678", False, False),
        ("phone_hint", "Подсказка под телефоном", "Ізраїльський номер або міжнародний із кодом країни.", False, True),
        ("submit_label", "Кнопка отправки заявки", "Надіслати заявку", True, False),
        ("bottom_note", "Дополнительный текст под формой", "", False, True),
    ]),
    ("9. Экран после регистрации и закрытая страница", "Основные сообщения уже редактируются выше: «Сообщение после регистрации» и «Сообщение о закрытии». Здесь — окружающие их заголовки и подписи.", [
        ("success_eyebrow", "Надпись над подтверждением", "ЗАЯВКУ ЗБЕРЕЖЕНО", False, False),
        ("success_heading", "Заголовок после регистрации", "Дякуємо, що Ви з нами!", True, False),
        ("success_note", "Дополнительная подпись после регистрации", "Це підтвердження отримання заявки. Воно не є квитком.", False, True),
        ("closed_eyebrow", "Надпись над сообщением о закрытии", "ПРИЙОМ ЗАЯВОК ЗАКРИТО", False, False),
        ("closed_heading", "Заголовок закрытой страницы", "До наступної зустрічі!", True, False),
    ]),
    ("10. Сообщения об ошибках формы", "Публичные подсказки при ошибках заполнения. Изменение текста не отключает проверки и защиту от дублей.", [
        ("error_title", "Заголовок сообщения об ошибках", "Перевірте, будь ласка, дані.", True, False),
        ("error_hint", "Пояснение к ошибкам полей", "Підказки є під відповідними полями.", False, False),
        ("phone_error", "Некорректный телефон", "Введіть дійсний номер телефону з кодом країни або ізраїльський номер.", True, True),
        ("duplicate_error", "Повторная заявка", "Заявку з таким email або телефоном для цієї сторінки вже отримано.", True, True),
        ("rate_limit_error", "Слишком частые попытки отправки", "Забагато спроб. Спробуйте ще раз за 10 хвилин.", True, True),
    ]),
]

COPY_FIELDS = {key: (label, default, required, multiline)
               for _, _, fields in COPY_GROUPS
               for key, label, default, required, multiline in fields}
DEFAULT_PUBLIC_COPY = {key: spec[1] for key, spec in COPY_FIELDS.items()}


def resolved_public_copy(overrides):
    values = DEFAULT_PUBLIC_COPY.copy()
    if isinstance(overrides, dict):
        for key, default in DEFAULT_PUBLIC_COPY.items():
            value = overrides.get(key, default)
            if (isinstance(default, bool) and isinstance(value, bool)) or (isinstance(default, str) and isinstance(value, str)):
                values[key] = value
    return values
