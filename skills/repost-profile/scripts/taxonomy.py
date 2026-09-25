"""Shared labels for the repost analysis: theme groups, Arabic names and chart colours."""

GROUPS = {
    "love_and_loss": {"romance_longing", "heartbreak_loss", "loneliness_isolation", "betrayal_trust",
                      "gender_relationships_dynamics", "marriage_dating_culture"},
    "wisdom_and_self": {"stoicism_patience", "motivation_ambition", "self_worth_boundaries", "life_lessons_wisdom",
                        "philosophy_existential", "religion_spirituality", "mental_health_mood", "kindness_humanity",
                        "friendship_loyalty", "family_parents", "parenting_children"},
    "study_work_tech": {"career_job_hunt", "study_university", "graduation_milestone", "programming_software", "ai_tools",
                        "tech_general", "data_science_math", "work_office_life", "money_economy"},
    "arabic_word_and_song": {"classical_poetry", "modern_poetry_prose", "music_song_appreciation", "arab_culture_heritage",
                             "language_linguistics"},
    "humor_and_daily": {"humor_absurd", "humor_relatable", "local_daily_life", "iraqi_daily_life", "society_critique",
                        "iraqi_society_critique", "social_media_meta", "nostalgia_childhood"},
    "animals": {"animals_cats", "animals_other"},
    "world_and_curiosity": {"science_curiosity", "history", "travel_places", "nature_scenery", "art_design_craft",
                            "film_tv_anime", "gaming", "chess", "sports_football", "food", "politics_news",
                            "health_fitness", "fashion_beauty", "cars_vehicles", "other"},
}
GROUP_AR = {
    "wisdom_and_self": "حكمة وتأمل", "love_and_loss": "حب وفقد", "study_work_tech": "دراسة وشغل وتقنية",
    "humor_and_daily": "ضحك ويوميات", "arabic_word_and_song": "شعر وطرب", "world_and_curiosity": "عالم وفضول",
    "animals": "حيوانات",
}
GROUP_TITLE = {
    "love_and_loss": "الحب والفقد والعتاب",
    "wisdom_and_self": "الحكمة والتأمل والنفس والإيمان",
    "study_work_tech": "الدراسة والشغل والتقنية",
    "humor_and_daily": "الضحك واليوميات والحنين",
    "arabic_word_and_song": "الشعر والطرب والكلمة",
    "world_and_curiosity": "الفضول والعالم",
    "animals": "الحيوانات",
    "mixed": "الفضول والعالم والحيوانات",
}
GROUP_COLOR = {
    "wisdom_and_self": "#5B7DB1", "love_and_loss": "#C0504D", "study_work_tech": "#4E9A6B",
    "humor_and_daily": "#E0A43A", "arabic_word_and_song": "#8064A2", "world_and_curiosity": "#4BACC6",
    "animals": "#9C8468",
}
EMO_AR = {
    "joy_amusement": "ضحك", "longing": "حنين", "love_tenderness": "حب وحنان", "sadness": "حزن",
    "bitterness_disillusion": "مرارة وخيبة", "hope": "أمل", "calm_peace": "سكينة", "pride": "فخر",
    "anxiety_stress": "قلق", "awe_wonder": "دهشة", "comfort": "طمأنينة", "neutral": "محايد",
    "embarrassment": "إحراج", "curiosity": "فضول", "anger_frustration": "غضب",
}
LANG_AR = {
    "english": "إنكليزي", "msa_classical": "فصحى", "iraqi_arabic": "عراقي", "levantine_arabic": "شامي",
    "gulf_arabic": "خليجي", "egyptian_arabic": "مصري", "maghrebi_arabic": "مغاربي", "mixed_arabic_english": "عربي وإنكليزي",
    "no_language": "بلا كلام", "other_language": "لغة أخرى", "other_arabic_dialect": "لهجة عربية أخرى",
}
MONTH_AR = {"01": "كانون الثاني", "02": "شباط", "03": "آذار", "04": "نيسان", "05": "أيار", "06": "حزيران",
            "07": "تموز", "08": "آب", "09": "أيلول", "10": "تشرين الأول", "11": "تشرين الثاني", "12": "كانون الأول"}
MONTH_SHORT = {"01": "ك2", "02": "شباط", "03": "آذار", "04": "نيسان", "05": "أيار", "06": "حزيران",
               "07": "تموز", "08": "آب", "09": "أيلول", "10": "ت1", "11": "ت2", "12": "ك1"}
WEEKDAYS = [("Saturday", "السبت"), ("Sunday", "الأحد"), ("Monday", "الاثنين"), ("Tuesday", "الثلاثاء"),
            ("Wednesday", "الأربعاء"), ("Thursday", "الخميس"), ("Friday", "الجمعة")]
ARABIC_LANGS = {"msa_classical", "iraqi_arabic", "levantine_arabic", "gulf_arabic", "egyptian_arabic", "maghrebi_arabic",
                "other_arabic_dialect", "mixed_arabic_english"}


def group_of(theme):
    return next((g for g, s in GROUPS.items() if theme in s), "world_and_curiosity")


def month_label(m):
    return f"{MONTH_SHORT[m[5:7]]} {m[2:4]}"


def month_long(m):
    return f"{MONTH_AR[m[5:7]]} {m[:4]}"


def date_ar(d):
    """YYYY-MM-DD as '20 آب 2025', which survives right-to-left layout unlike ISO dates."""
    return f"{int(d[8:10])} {MONTH_AR[d[5:7]]} {d[:4]}" if d and len(d) >= 10 else (d or "")
