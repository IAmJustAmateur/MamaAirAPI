from django.db import migrations

MESSAGES_EN = {
    1: "Your baby’s journey begins with fertilization. The sperm and egg come together to form a tiny cell that starts dividing into many cells.",
    2: "The tiny cluster of cells moves toward the uterus, where it will attach and begin developing.",
    3: "The tiny bundle attaches to the lining of your uterus, and the beginnings of the placenta start to form to nourish your baby.",
    4: "The tiny ball of cells, now called a blastocyst, begins to develop a protective sac around it — the amniotic sac — to cushion your baby.",
    5: "The brain and spinal cord begin to form. The heart starts beating and pumping blood.",
    6: "Little arm and leg buds appear. Your baby’s circulatory system is forming, and the heart starts to pump blood.",
    7: "Your baby’s arms and legs grow, and the head becomes larger compared to the rest of the body. Early facial features start to form.",
    8: "Your baby’s major organs and body systems are developing. Hands and feet are taking shape, and the umbilical cord is fully formed.",
    9: "Your baby is now officially a fetus. The eyes, ears, and mouth are becoming more defined, and the tail-like structure is starting to disappear.",
    10: "The arms, hands, and feet are fully formed. Fingernails and toenails begin to develop.",
    11: "Your baby starts moving its mouth and fingers. Tiny movements begin, and bones begin to harden.",
    12: "All major organs and limbs are in place. Your baby is now swallowing and peeing amniotic fluid.",
    13: "Your baby’s body is becoming more proportionate. The skin is thickening, and it can make more purposeful movements.",
    14: "Your baby’s skin is developing, and fine hair starts to grow. It can bring fingers to its mouth and make facial expressions.",
    15: "The fetus starts moving more intentionally, like sucking its thumb. The internal organs continue to mature.",
    16: "Your baby’s skin is becoming thicker, and it starts reacting to sounds, even though its eyes are still closed.",
    17: "Your baby’s bones are hardening, and it is starting to put on some fat. It can now hear sounds from the outside world.",
    18: "You may start feeling your baby’s movements, and it is now stronger. Your baby’s nervous system is also continuing to develop.",
    19: "The baby can now blink, and its skin is covered with soft hair. It has its own unique set of fingerprints.",
    20: "You’re halfway through! Your baby is moving more, and you might be able to feel kicks. It’s the size of a banana.",
    21: "Your baby’s grasp reflex is developing, and it’s becoming more active. It can also feel touch.",
    22: "Your baby’s skin is thin, and it’s starting to gain more fat. It’s reacting to sounds and movements.",
    23: "If born prematurely, your baby may survive with special care. It’s growing rapidly and getting stronger.",
    24: "The baby’s lungs are developing, but are not yet ready for breathing outside the womb.",
    25: "Your baby is gaining fat and becoming plumper. The nervous system is quickly maturing, and it is moving more.",
    26: "Your baby’s skin is starting to get color, and its lungs begin making surfactant, a substance that helps it breathe after birth.",
    27: "Your baby can open its eyes and blink. It has eyelashes, and is developing more of its senses.",
    28: "Your baby is getting ready for birth and may be turning head-down. It’s gaining weight quickly and maturing.",
    29: "Your baby’s skin is becoming less wrinkled as it gains more fat. The brain is developing rapidly, and it’s getting stronger.",
    30: "Your baby can now regulate its body temperature. It has sleep-wake cycles, and you may notice more distinct movements.",
    31: "The brain is maturing rapidly, and your baby is becoming more aware of its surroundings.",
    32: "Your baby’s skin is no longer transparent. Most of the internal organs are fully developed and ready for birth.",
    33: "Your baby’s bones are hardening. It is packing on more fat and getting ready for the big day.",
    34: "Your baby’s skin is thickening, and it’s gaining more body fat. The baby is now very close to being ready for birth.",
    35: "The brain is growing quickly. Your baby is now more developed and continues to prepare for life outside the womb.",
    36: "Your baby is now fully formed. The lungs and brain are still maturing, but your baby is ready for birth.",
    37: "Your baby is full-term! It’s gaining about half a pound a week and is preparing for birth.",
    38: "Your baby’s body is filling out, and it’s almost ready to meet you.",
    39: "Your baby is now considered full-term and ready to be born. It’s gaining weight and maturing in preparation for delivery.",
    40: "Your baby is ready to be born! It’s your due date week, so get ready for the big moment!",
}


def forwards(apps, schema_editor):
    MamaAirMessage = apps.get_model("recommendations", "MamaAirMessage")
    to_create = []
    for week, text in MESSAGES_EN.items():
        obj, created = MamaAirMessage.objects.get_or_create(
            week=week,
            locale="en",
            defaults={"text": text, "is_active": True, "version": 1},
        )
        if not created:
            # если хотим синхронизировать текст по миграции
            obj.text = text
            obj.is_active = True
            if obj.version < 1:
                obj.version = 1
            obj.save(update_fields=["text", "is_active", "version", "updated_at"])


def backwards(apps, schema_editor):
    MamaAirMessage = apps.get_model("recommendations", "MamaAirMessage")
    MamaAirMessage.objects.filter(locale="en", week__in=MESSAGES_EN.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("recommendations", "0003_mamaairmessage"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
