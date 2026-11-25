"""Default studio texts in English (used when IDIOMA=en). Starting templates only: the artist
should review them (ideally with legal advice) in Settings before using them."""

TEXTO_CONSENTIMIENTO = """\
INFORMED CONSENT FOR TATTOOING

I declare that:

1. I am at least 18 years old and have shown valid photo ID.
2. I am not under the influence of alcohol or any other substance.
3. I have honestly disclosed my allergies, medication and relevant health conditions (diabetes, bleeding disorders, epilepsy, skin conditions, pregnancy or breastfeeding).
4. I understand that tattooing is a permanent procedure and that there are risks such as infection, allergic reaction to pigments, irregular healing or color variation.
5. I have reviewed and approved the design, placement and size.
6. I agree to follow the aftercare instructions I have been given. The final result depends partly on that aftercare.
7. I understand that the deposit is non-refundable except as stated in the studio policy.
8. I authorize the studio to keep this document and my information for the period required by applicable health regulations.

I sign this consent freely and voluntarily.
"""

TEXTO_PRIVACIDAD = """\
We only use your information to handle your request and your appointment. We don't share it with third parties. \
If you tick the news box, we may message you from time to time (birthday wishes, available flash, open slots). \
You can opt out at any time by replying to any message."""

POLITICA_SENAS = """\
To book a date we ask for a deposit that is deducted from the final price. The deposit is not refunded \
if you cancel with less than 48 hours' notice or don't show up; you can reschedule once if you let us know in time."""

TEXTO_CUIDADOS = """\
Wash the tattoo with lukewarm water and fragrance-free soap 2-3 times a day, pat it dry and apply a thin \
layer of ointment. No pools, ocean, direct sun or scratching for the first 2-3 weeks."""

RESERVA_BIENVENIDA = """\
Tell me about your idea in as much detail as you can. I review every request personally and will reply \
by WhatsApp or SMS within a few days."""

IA_TONO = """\
Friendly, direct and warm. Short sentences, no jargon and not too many emojis \
(one per message at most). Never sounds corporate or pushy."""

POR_CAMPO = {
    "texto_consentimiento": TEXTO_CONSENTIMIENTO,
    "texto_privacidad": TEXTO_PRIVACIDAD,
    "politica_senas": POLITICA_SENAS,
    "texto_cuidados": TEXTO_CUIDADOS,
    "reserva_bienvenida": RESERVA_BIENVENIDA,
    "ia_tono": IA_TONO,
}
