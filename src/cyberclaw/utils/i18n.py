"""i18n Localization Engine for CyberClaw."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Core dictionary of translations
TRANSLATIONS: dict[str, dict[str, str]] = {
    "bn": {
        "welcome": "CyberClaw CLI-তে আপনাকে স্বাগতম!",
        "wizard_step_provider": "LLM Provider কনফিগারেশন ধাপ",
        "enter_key": "অনুগ্রহ করে {provider} এর জন্য আপনার আসল API Key টাইপ করুন",
        "doctor_healthy": "সব চেক পাস হয়েছে - CyberClaw সম্পূর্ণ সুস্থ!",
        "doctor_issues": "নিচের {count}টি সমস্যা পাওয়া গিয়েছে:",
        "missing_dir": "হারিয়ে যাওয়া ডিরেক্টরি: {dir}",
        "fixed_key": "সফলভাবে {provider} এর API Key ঠিক করা হয়েছে",
        "tui_title": "CyberClaw ইন্টারেক্টিভ TUI ড্যাশবোর্ড",
        "tui_nav": "ট্যাব অথবা সংখ্যা বাটন প্রেস করে নেভিগেট করুন:",
        "option_chat": "১. লাইভ চ্যাট সেশন",
        "option_doctor": "২. সিস্টেম ডক্টর চেক",
        "option_plugins": "৩. প্লাগইন ম্যানেজার",
        "option_migrate": "৪. ডাটা মাইগ্রেশন টুলস",
        "option_exit": "৫. প্রস্থান (Exit)",
    },
    "es": {
        "welcome": "¡Bienvenido a CyberClaw CLI!",
        "wizard_step_provider": "Paso de configuración del proveedor LLM",
        "enter_key": "Por favor ingrese su API Key real para {provider}",
        "doctor_healthy": "¡Todas las comprobaciones pasaron - CyberClaw está sano!",
        "doctor_issues": "Se encontraron los siguientes {count} problemas:",
        "missing_dir": "Directorio faltante: {dir}",
        "fixed_key": "API Key corregida para {provider}",
        "tui_title": "Panel interactivo TUI de CyberClaw",
        "tui_nav": "Use números o teclas para navegar:",
        "option_chat": "1. Chat en vivo",
        "option_doctor": "2. Diagnóstico del sistema",
        "option_plugins": "3. Administrador de plugins",
        "option_migrate": "4. Migración de datos",
        "option_exit": "5. Salir",
    },
    "fr": {
        "welcome": "Bienvenue dans CyberClaw CLI !",
        "wizard_step_provider": "Étape de configuration du fournisseur LLM",
        "enter_key": "Veuillez saisir votre clé API réelle pour {provider}",
        "doctor_healthy": "Tous les contrôles ont réussi - CyberClaw est en bonne santé !",
        "doctor_issues": "Les {count} problèmes suivants ont été trouvés :",
        "missing_dir": "Dossier manquant : {dir}",
        "fixed_key": "Clé API corrigée pour {provider}",
        "tui_title": "Tableau de bord interactif CyberClaw TUI",
        "tui_nav": "Utilisez les touches numériques pour naviguer :",
        "option_chat": "1. Chat en direct",
        "option_doctor": "2. Diagnostic du système",
        "option_plugins": "3. Gestionnaire de plugins",
        "option_migrate": "4. Outils de migration",
        "option_exit": "5. Quitter",
    },
    "de": {
        "welcome": "Willkommen bei CyberClaw CLI!",
        "wizard_step_provider": "Konfigurationsschritt für LLM-Provider",
        "enter_key": "Bitte geben Sie Ihren echten API-Schlüssel für {provider} ein",
        "doctor_healthy": "Alle Überprüfungen bestanden - CyberClaw ist gesund!",
        "doctor_issues": "Die folgenden {count} Probleme wurden gefunden:",
        "missing_dir": "Fehlendes Verzeichnis: {dir}",
        "fixed_key": "API-Schlüssel für {provider} korrigiert",
        "tui_title": "Interaktives CyberClaw TUI-Dashboard",
        "tui_nav": "Nutzen Sie Zifferntasten zur Navigation:",
        "option_chat": "1. Live-Chat",
        "option_doctor": "2. System-Doctor-Check",
        "option_plugins": "3. Plugin-Manager",
        "option_migrate": "4. Datenmigration",
        "option_exit": "5. Beenden",
    }
}

class Translator:
    """Manages translation of keys into selected languages."""
    
    def __init__(self, language: str = "en"):
        self.language = language.lower()

    def translate(self, key: str, **kwargs: Any) -> str:
        """Translate key to targeted language, falling back to English."""
        lang_dict = TRANSLATIONS.get(self.language, {})
        text = lang_dict.get(key)
        
        if text is None:
            # Fallback to English/Defaults
            fallback_dict = {
                "welcome": "Welcome to CyberClaw CLI!",
                "wizard_step_provider": "LLM Provider configuration step",
                "enter_key": "Please enter your real API key for {provider}",
                "doctor_healthy": "All checks passed - CyberClaw is healthy!",
                "doctor_issues": "Found the following {count} issue(s):",
                "missing_dir": "Missing workspace directory: {dir}",
                "fixed_key": "Fixed API key for {provider}",
                "tui_title": "CyberClaw Interactive TUI Dashboard",
                "tui_nav": "Navigate by typing an option number:",
                "option_chat": "1. Live Chat Session",
                "option_doctor": "2. Run System Doctor",
                "option_plugins": "3. Plugin Manager",
                "option_migrate": "4. Database/Config Migration",
                "option_exit": "5. Exit Dashboard",
            }
            text = fallback_dict.get(key, key)
            
        try:
            return text.format(**kwargs)
        except Exception:
            return text

# Global translator helper
_t_cache: dict[str, Translator] = {}

def get_translator(lang: str) -> Translator:
    """Get or create Translator instance for a language."""
    if lang not in _t_cache:
        _t_cache[lang] = Translator(lang)
    return _t_cache[lang]
