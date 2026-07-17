"""shows/demo/strings.py — every user-facing string for the demo show "רדאר" (Hebrew)."""

from showkit import Strings

STRINGS = Strings(
    # --- Telegram digest ---
    tg_header_prefix="🎙️ רדאר",
    tg_episode_word="פרק",
    tg_deepdive_label="🔥 Deep Dive:",
    tg_listen_label="🔗 להאזנה: ",
    tg_returning_word="פרק",
    tg_empty_state="אין ישויות בולטות להעמקה בפרק זה — הכל שמור במאגר.",
    tg_db_more="🗂️ +{k} ישויות נוספות במאגר → {link}",
    tg_db_all="🗂️ כל הישויות במאגר → {link}",

    # --- approval flow ---
    approve_btn="✅ אשר ושלח לערוץ",
    reject_btn="❌ דחה",
    toast_unauthorized="לא מורשה",
    toast_already_sent="כבר נשלח",
    toast_no_channel="ערוץ לא מוגדר",
    toast_sent="נשלח לערוץ ✅",
    toast_rejected="נדחה",
    disabled_sent="✅ נשלח לערוץ",
    disabled_rejected="❌ נדחה",

    # --- Notion episode-page body ---
    notion_summary_heading="📝 סיכום",
    notion_topics_heading="🧭 נושאים בפרק",
    notion_entities_heading="🔑 ישויות",
    notion_transcript_title="תמלול",
    notion_episode_context_word="פרק",

    # --- "Learn" Perplexity deep-link ---
    learn_prompt_template=(
        "למד אותי על {subject} שלב אחר שלב: רקע קצר, למה זה משמעותי, 3 נקודות מפתח, "
        "דימוי פשוט אחד, ושאלה קצרה לבדיקת הבנה בסוף."
    ),
    learn_prompt_context_template=' בפודקאסט "{show}" נאמר עליו: "{ctx}" — התייחס גם לכך.',
    learn_prompt_suffix=" בעברית, פשוט ונגיש.",

    # --- email (disabled scaffold) ---
    email_subject_template="{show} — {episode_word} {num}",
    email_body_template="<p>חולצו {n} ישויות.</p>",
    email_open_notion="פתח ב-Notion",

    # --- entity resolution pass ---
    resolve_items_prefix="ישויות לפתרון:",
    resolve_preview_header="<b>🔎 תיקוני האחדה (לבדיקה):</b>",
    resolve_note_dropped="⚠️ הושמט (לא ישות): {name}",
    resolve_note_merged="🔗 אוחד: {orig} → {target} [{confidence}]",
    resolve_note_renamed="✏️ שם תוקן: {orig} → {new} [{confidence}]",
    resolve_note_low_conf="❓ ביטחון נמוך: {name} (key={key})",

    # --- extraction user-turn + meta-context repair ---
    extract_transcript_prefix="תמלול הפרק:",
    extract_shownotes_note=(
        "\n\nShownotes (לשימוש רק למילוי link כשכתובת ממופה בבירור לישות, "
        "ולעזרה באיות שמות — לעולם אל תמציא):\n"
    ),
    regen_items_prefix="פריטים לתיקון:",
    # Hebrew "meta" phrasing (describes who said/wrote it) -> auto-repaired. Empty
    # disables the feature; kept on for Hebrew because prompt rules alone leaked it.
    meta_context_patterns=(
        r"שוחח", r"כתב\b", r"ציין ש", r"מזכיר ש", r"מציין ש", r"ממליץ להאזין",
        r"אמר ש", r"סיפר ש", r"תוהה", r"מוזכר כ", r"מתואר כ", r"נחשב ל",
    ),

    # --- failure alerts ---
    alert_episode_failed_template="🚨 <b>{show} — episode {num} failed</b>\n",
    alert_auto_review_failed_template="🚨 <b>{show} — auto_review נכשל</b>\n",

    # --- watchdog dead-man alerts ---
    watchdog_empty_feed_template="⚠️ {show} watchdog: הפיד לא החזיר פרקים — בדוק את ה-RSS/pipeline.",
    watchdog_not_processed_template=(
        "⚠️ {show} — פרק {num} עדיין לא עובד עד הצהריים (שישי).\n"
        "הטריגר השבועי (Cloud Scheduler → pipeline) כנראה לא רץ.\n"
        "הרצה ידנית: gh workflow run pipeline.yml -f mode=auto -f episode=1"
    ),
)
