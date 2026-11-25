"""Starter content in English (used when IDIOMA=en). Same keys as predeterminados.py."""

PLANTILLAS = {
    "recordatorio": (
        "Appointment reminder",
        "Hi {nombre}! Just a reminder of your appointment at {estudio} on {fecha_cita} at {hora_cita}. "
        "If you need to confirm, change or cancel it, you can do it here: {enlace_cita}\nSee you soon!",
    ),
    "dia1": (
        "Aftercare · day 1",
        "Hi {nombre} 🖤 How's the new tattoo? Today, wash it with lukewarm water and fragrance-free soap, pat it dry "
        "and apply a thin layer of ointment. Message me with any questions.",
    ),
    "dia3": (
        "Aftercare · day 3",
        "Hi {nombre}! Day 3: some itching or light peeling is normal. Don't scratch or pick at it and keep using a "
        "thin layer of ointment. How's it looking?",
    ),
    "semana2": (
        "Aftercare · week 2",
        "{nombre}, it's been two weeks since your tattoo. If it's healing well, could you send me a photo? "
        "I love seeing how they settle.",
    ),
    "retoque": (
        "Touch-up offer (30 days)",
        "Hi {nombre}, it's been a month since your tattoo. If any area needs a touch-up, message me and we'll find "
        "a time. Touch-ups are included.",
    ),
    "hueco": (
        "Open slot for the waiting list",
        "Hi {nombre}! A slot just opened up on {fecha_cita} at {hora_cita}. Does that work for you? "
        "If you reply soon, I'll hold it for you.",
    ),
    "aprobada": (
        "Request accepted",
        "Hi {nombre}! Thanks for reaching out, I love your idea. Which days work best for you? "
        "I'll suggest a date and send you the deposit details.",
    ),
    "rechazada": (
        "Request not accepted",
        "Hi {nombre}, thanks for thinking of me for your tattoo. I can't take on that project right now, "
        "but I wish you the best with it.",
    ),
    "cumple": ("Happy birthday", "Happy birthday, {nombre}! 🎉 Have an amazing day. Hugs from {artista}."),
    "aniversario": (
        "Tattoo anniversary",
        "{nombre}, it's been {aniversario} since your tattoo “{tatuaje}”! Thanks for trusting me. "
        "If you have a photo of how it looks now, I'd love to see it.",
    ),
    "reactivacion": (
        "We miss you",
        "Hi {nombre}! It's been a while. I have openings in the coming weeks if you're up for something new "
        "or a touch-up. Tell me your idea here: {enlace_reserva}",
    ),
    "campana": (
        "Flash available",
        "Hi {nombre}! I have new flash designs available this month. Want me to send you the catalog? {enlace_reserva}",
    ),
    "navidad": ("Christmas", "Merry Christmas, {nombre}! 🎄 Thanks for being part of this year at {estudio}."),
    "anio_nuevo": (
        "New Year",
        "Happy New Year, {nombre}! May this year be full of great ideas (and ink). — {artista}",
    ),
    "san_valentin": (
        "Valentine's Day",
        "Happy Valentine's Day, {nombre} 🖤 This month I have designs for couples and friends. Are you in?",
    ),
    "madre": (
        "Mother's Day",
        "{nombre}, happy Mother's Day! If you'd like to give (or treat yourself to) a tattoo, I have gift cards.",
    ),
    "padre": (
        "Father's Day",
        "{nombre}, happy Father's Day! Studio gift cards make a great Sunday plan.",
    ),
    "dia_tatuaje": ("Tattoo Day", "Today is National Tattoo Day 🖤 Thanks for carrying my work with you, {nombre}."),
    "halloween": (
        "Halloween",
        "Happy Halloween, {nombre}! 🎃 This week I have seasonal designs. Want me to save one for you?",
    ),
    "gracias": ("Thanksgiving", "Happy Thanksgiving, {nombre}. Thank you for your trust this year."),
    "viernes13": (
        "Friday the 13th",
        "Friday the 13th, {nombre}! 🔮 Special flash today only. Message me to book your spot.",
    ),
}

CUIDADOS = {"dia1": "Day 1", "dia3": "Day 3", "semana2": "Week 2", "retoque": "Touch-up"}

FECHAS = {
    "anio_nuevo": "New Year's Day",
    "san_valentin": "Valentine's Day",
    "madre": "Mother's Day (US)",
    "padre": "Father's Day (US)",
    "dia_tatuaje": "National Tattoo Day",
    "halloween": "Halloween",
    "gracias": "Thanksgiving",
    "navidad": "Christmas",
    "viernes13": "Friday the 13th (flash day)",
}

TIPOS = {"Consulta": "Consultation", "Sesión": "Session", "Sesión larga": "Long session", "Retoque": "Touch-up"}
