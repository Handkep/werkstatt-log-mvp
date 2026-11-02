"""Statische UI- und Raum-Konfigurationsdaten."""

FUNNY_NAME_EXAMPLES = [
    "Albert Einstein",
    "Isaac Newton",
    "Ada Lovelace",
    "Grace Hopper",
    "Alan Turing",
    "Linus Torvalds",
    "Margaret Hamilton",
    "Marie Curie",
    "Nikola Tesla",
    "Robert C. Martin",
    "Bjarne Stroustrup",
    "Tim Berners-Lee",
    "Edsger Dijkstra",
    "Guido van Rossum",
    "Max Planck",
    "Stephen Hawking",
    "Charles Darwin",
    "Alexander Fleming",
    "Carl Friedrich Gauß",
    "Niels Bohr",
]

HOUSE_GROUPS = ["TH", "GH", "PH"]

WORKSHOP_CONDITIONS = [
    "Sauber",
    "Aufräumen nötig",
    "Problem/Defekt",
]

ROOM_DEFINITIONS = [
    {
        "slug": "werkstatt",
        "name": "Werkstatt",
        "description": "Werkzeuge, Maschinen und Arbeitsflächen dokumentieren.",
        "intro_text": "Dokumentiere kurz die Nutzung der Werkstatt.",
        "condition_label": "Zustand der Werkstatt",
        "remark_placeholder": "z. B. Werkbank benutzt, alles sauber hinterlassen",
        "checklist_title": "Bitte die Werkstatt so verlassen",
        "checklist_intro": "Ein letzter kurzer Check hilft allen, die die Werkstatt nach dir nutzen.",
        "checklist_items": [
            "Werkzeug zurückräumen",
            "Arbeitsflächen sauber hinterlassen",
            "Müll und Restmaterial entsorgen",
            "Fenster schließen und Licht ausschalten",
            "Tür ordentlich schließen",
        ],
        "extra_fields": [],
        "sort_order": 10,
        "is_active": 1,
    },
    {
        "slug": "dachterrasse",
        "name": "Dachterrasse",
        "description": "Ordnung, Sauberkeit und Rücksicht auf die gemeinsame Terrasse festhalten.",
        "intro_text": "Dokumentiere kurz die Nutzung der Dachterrasse.",
        "condition_label": "Zustand der Dachterrasse",
        "remark_placeholder": "z. B. Stühle genutzt, alles wieder ordentlich gestellt",
        "checklist_title": "Bitte die Dachterrasse so verlassen",
        "checklist_intro": "So bleibt die Dachterrasse für alle direkt wieder nutzbar.",
        "checklist_items": [
            "Möbel ordentlich zurückstellen",
            "Tische sauber hinterlassen",
            "Leergut, Müll und Asche entfernen",
            "Licht und elektrische Geräte ausschalten",
            "Auf einen ruhigen, aufgeräumten Gesamteindruck achten",
        ],
        "extra_fields": [],
        "sort_order": 20,
        "is_active": 1,
    },
    {
        "slug": "sommerkueche",
        "name": "Sommerküche",
        "description": "Nutzung, Sauberkeit und Zustand der gemeinsamen Sommerküche erfassen.",
        "intro_text": "Dokumentiere kurz die Nutzung der Sommerküche.",
        "condition_label": "Zustand der Sommerküche",
        "remark_placeholder": "z. B. Herd benutzt, Flächen gereinigt, alles trocken hinterlassen",
        "checklist_title": "Bitte die Sommerküche so verlassen",
        "checklist_intro": "Mit ein paar Handgriffen ist die Sommerküche sofort wieder einsatzbereit.",
        "checklist_items": [
            "Benutztes Geschirr und Werkzeug reinigen",
            "Arbeitsflächen abwischen",
            "Lebensmittelreste und Müll entsorgen",
            "Wasser, Strom und Geräte prüfen",
            "Alles ordentlich und hygienisch hinterlassen",
        ],
        "extra_fields": [],
        "sort_order": 30,
        "is_active": 1,
    },
    {
        "slug": "sauna",
        "name": "Sauna",
        "description": "Sauberkeit, Nutzung und eventuelle Auffälligkeiten in der Sauna festhalten.",
        "intro_text": "Dokumentiere kurz die Nutzung der Sauna.",
        "condition_label": "Zustand der Sauna",
        "remark_placeholder": "z. B. Sauna genutzt, Holz trocken, keine Auffälligkeiten",
        "checklist_title": "Bitte die Sauna so verlassen",
        "checklist_intro": "So bleibt die Sauna hygienisch und bereit für die nächsten Nutzerinnen und Nutzer.",
        "checklist_items": [
            "Benutzte Flächen trocken hinterlassen",
            "Handtücher und persönliche Dinge mitnehmen",
            "Müll entsorgen",
            "Licht und Technik prüfen",
            "Ruhe und Sauberkeit im Raum wiederherstellen",
        ],
        "extra_fields": [],
        "sort_order": 40,
        "is_active": 1,
    },
    {
        "slug": "ruheraum",
        "name": "Ruheraum",
        "description": "Den Ruheraum ordentlich, ruhig und angenehm für die nächsten Personen dokumentieren.",
        "intro_text": "Dokumentiere kurz die Nutzung des Ruheraums.",
        "condition_label": "Zustand des Ruheraums",
        "remark_placeholder": "z. B. Matten genutzt, alles ruhig und ordentlich hinterlassen",
        "checklist_title": "Bitte den Ruheraum so verlassen",
        "checklist_intro": "Ein ruhiger und gepflegter Raum macht den Unterschied für die nächsten Personen.",
        "checklist_items": [
            "Liegen, Kissen oder Decken ordentlich zurücklegen",
            "Persönliche Dinge vollständig mitnehmen",
            "Müll entsorgen",
            "Licht und Fenster prüfen",
            "Den Raum ruhig, sauber und einladend hinterlassen",
        ],
        "extra_fields": [],
        "sort_order": 50,
        "is_active": 1,
    },
]

NAV_GROUPS = {
    "public": [
        {"id": "rooms", "icon": "door-open", "label": "Räume", "href": "/"},
        {"id": "logbook", "icon": "notebook-pen", "label": "Logbuch", "href": "/logbuch"},
        {"id": "help", "icon": "circle-question-mark", "label": "Hilfe & Infos", "href": "/hilfe"},
    ],
    "admin": [
        {"id": "admin", "label": "Einträge", "href": "/admin"},
        {"id": "admin_messages", "label": "Nachrichten", "href": "/admin/nachrichten"},
        {"id": "room_access", "label": "QR-Zugänge", "href": "/admin/raumzugaenge"},
    ],
    "meta": [
        {"id": "privacy", "label": "Datenschutz", "href": "/datenschutz"},
    ],
}


# Reine Darstellung; unbekannte Raum-Slugs verwenden eine offene Tür.
ROOM_ICONS = {
    "werkstatt": "wrench",
    "dachterrasse": "fence",
    "sommerkueche": "cooking-pot",
    "sauna": "heater",
    "ruheraum": "armchair",
}
