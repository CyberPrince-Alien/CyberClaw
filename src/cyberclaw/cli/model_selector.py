"""
CyberClaw Premium Model Selection Wizard — V9 Style
=====================================================
Inspired by Cyber Prince CLI V9's premium launcher.
Features:
  - Jungle gradient CYBERCLAW ANSI banner
  - Hardware spec detection (RAM, CPU, GPU, tier classification)
  - Interactive local Ollama model management (list, pull, uncensored)
  - Cloud provider menus (Google/Gemini, OpenAI, Groq, OpenRouter, NVIDIA, DeepSeek, Anthropic, Together AI, SambaNova)
  - Instant API key validation
  - Safe YAML merge to config.user.yaml
  - Auto-launch chat session after model selection
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box

console = Console()


# ═══════════════════════════════════════════════════════════════════════
#  SECTION 1: JUNGLE GRADIENT CYBERCLAW BANNER
# ═══════════════════════════════════════════════════════════════════════

CYBERCLAW_LOGO_LINES = [
    " ██████╗██╗   ██╗██████╗ ███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗",
    "██╔════╝╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║",
    "██║      ╚████╔╝ ██████╔╝█████╗  ██████╔╝██║     ██║     ███████║██║ █╗ ██║",
    "██║       ╚██╔╝  ██╔══██╗██╔══╝  ██╔══██╗██║     ██║     ██╔══██║██║███╗██║",
    "╚██████╗   ██║   ██████╔╝███████╗██║  ██║╚██████╗███████╗██║  ██║╚███╔███╔╝",
    " ╚═════╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ ",
]

# Jungle gradient: dark forest → emerald → bright lime
JUNGLE_GRADIENT_COLORS = [
    (10, 80, 30),     # Deep dark forest
    (20, 120, 50),    # Dark jungle
    (30, 160, 70),    # Forest green
    (0, 210, 100),    # Emerald
    (0, 240, 120),    # Bright emerald
    (80, 255, 160),   # Lime green
]

BORDER_COLOR = (0, 180, 80)
READY_COLOR = (50, 255, 130)
SOFT_COLOR = (120, 255, 180)


def _rgb(r: int, g: int, b: int) -> str:
    return f"rgb({r},{g},{b})"


def print_cyberclaw_banner() -> None:
    """Print a gorgeous center-aligned CYBERCLAW banner with jungle gradient."""
    term_width = shutil.get_terminal_size((100, 30)).columns
    border_style = _rgb(*BORDER_COLOR)
    ready_style = _rgb(*READY_COLOR)
    soft_style = _rgb(*SOFT_COLOR)

    border_len = max(len(line) for line in CYBERCLAW_LOGO_LINES) + 4
    border_line = "═" * border_len

    console.print()
    console.print(Text(border_line, style=border_style), justify="center")
    console.print()

    for i, line in enumerate(CYBERCLAW_LOGO_LINES):
        color = JUNGLE_GRADIENT_COLORS[i % len(JUNGLE_GRADIENT_COLORS)]
        style = f"bold {_rgb(*color)}"
        console.print(Text(line, style=style), justify="center")

    console.print()
    console.print(Text(border_line, style=border_style), justify="center")
    console.print()

    ready_text = Text()
    ready_text.append("█ READY", style=f"bold {ready_style}")
    ready_text.append(" — CyberClaw AI Online", style=soft_style)
    console.print(ready_text, justify="center")
    console.print()


# ═══════════════════════════════════════════════════════════════════════
#  SECTION 2: HARDWARE SPEC DETECTION
# ═══════════════════════════════════════════════════════════════════════

def _get_total_ram_gb() -> float:
    """Get total system RAM in GB."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return round(int(result.stdout.strip()) / (1024 ** 3), 1)
        else:
            import resource
            # fallback for Linux/Mac
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        return round(int(line.split()[1]) / (1024 * 1024), 1)
    except Exception:
        pass
    # Ultimate fallback
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        return 0.0


def _get_free_ram_gb() -> float:
    """Get free system RAM in GB."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return round(int(result.stdout.strip()) / (1024 * 1024), 1)
    except Exception:
        pass
    return 0.0


def _get_cpu_info() -> tuple[str, int]:
    """Get CPU model name and core count."""
    cpu_model = platform.processor() or "Unknown CPU"
    cpu_cores = os.cpu_count() or 1
    # Try to get a better name on Windows
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor).Name"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                cpu_model = result.stdout.strip()
    except Exception:
        pass
    return cpu_model, cpu_cores


def _get_gpu_info() -> tuple[str | None, float | None]:
    """Get GPU name and VRAM in GB (Windows-only PowerShell)."""
    gpu_name = None
    gpu_vram_gb = None
    if sys.platform != "win32":
        return gpu_name, gpu_vram_gb
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = result.stdout.strip()

        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty AdapterRAM"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            vram_bytes = int(result.stdout.strip())
            if vram_bytes > 0:
                gpu_vram_gb = round(vram_bytes / (1024 ** 3), 1)
    except Exception:
        pass
    return gpu_name, gpu_vram_gb


def _classify_tier(total_ram_gb: float, gpu_vram_gb: float | None) -> tuple[str, str]:
    """Classify system capability tier and provide recommendation."""
    if total_ram_gb >= 32 and gpu_vram_gb and gpu_vram_gb >= 8:
        return "ULTRA", "Your system can handle large 70B+ models. Recommended: cogito:70b, deepseek-v3.1:671b-cloud"
    elif total_ram_gb >= 16:
        return "HIGH", "Good system! Recommended: llama3.1:8b, qwen2.5-coder:7b, gemma4:12b"
    elif total_ram_gb >= 8:
        return "MEDIUM", "Moderate system. Recommended: phi3:mini, tinyllama, qwen2.5-coder:3b"
    else:
        return "LIGHT", "Limited RAM. Recommended: tinyllama:latest, phi3:mini (smallest models)"


def detect_and_display_specs() -> dict[str, Any]:
    """Detect hardware specs and display a premium Rich panel."""
    total_ram = _get_total_ram_gb()
    free_ram = _get_free_ram_gb()
    cpu_model, cpu_cores = _get_cpu_info()
    gpu_name, gpu_vram = _get_gpu_info()
    tier, recommendation = _classify_tier(total_ram, gpu_vram)

    table = Table(
        title="⚡ System Specifications",
        box=box.ROUNDED,
        title_style="bold rgb(0,230,110)",
        border_style="rgb(0,180,80)",
        show_header=True,
        header_style="bold rgb(80,255,160)",
    )
    table.add_column("Component", style="rgb(120,255,180)", min_width=12)
    table.add_column("Details", style="bold white", min_width=40)
    table.add_row("RAM", f"{total_ram} GB total / {free_ram} GB free")
    table.add_row("CPU", f"{cpu_model} ({cpu_cores} cores)")
    if gpu_name:
        gpu_str = gpu_name
        if gpu_vram:
            gpu_str += f" ({gpu_vram} GB VRAM)"
        table.add_row("GPU", gpu_str)
    else:
        table.add_row("GPU", "Not detected")
    table.add_row("Tier", f"[bold rgb(0,255,136)][{tier}][/bold rgb(0,255,136)]")

    console.print(table)
    console.print(f"  [rgb(120,255,180)]💡 {recommendation}[/rgb(120,255,180)]")
    console.print()

    return {
        "total_ram_gb": total_ram,
        "free_ram_gb": free_ram,
        "cpu_model": cpu_model,
        "cpu_cores": cpu_cores,
        "gpu_name": gpu_name,
        "gpu_vram_gb": gpu_vram,
        "tier": tier,
        "recommendation": recommendation,
    }


# ═══════════════════════════════════════════════════════════════════════
#  SECTION 3: OLLAMA INTEGRATION
# ═══════════════════════════════════════════════════════════════════════

def _ollama_is_running() -> bool:
    """Check if Ollama API is reachable."""
    try:
        req = Request("http://localhost:11434/api/tags", method="GET")
        with urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _get_ollama_installed_models() -> list[dict[str, str]]:
    """Fetch installed Ollama models via API."""
    try:
        req = Request("http://localhost:11434/api/tags", method="GET")
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            models = data.get("models", [])
            return [
                {
                    "name": m.get("name", "unknown"),
                    "size": f"{m.get('size', 0) / (1024**3):.1f}GB",
                }
                for m in models
            ]
    except Exception:
        return []


def _ollama_pull_model(model_name: str) -> bool:
    """Pull an Ollama model with live terminal progress."""
    try:
        console.print(f"\n  [rgb(0,230,110)]⬇️  Pulling model: {model_name}...[/rgb(0,230,110)]")
        console.print("  [dim]This may take several minutes depending on model size and connection speed.[/dim]\n")
        result = subprocess.run(
            ["ollama", "pull", model_name],
            timeout=1800,  # 30 min timeout
        )
        return result.returncode == 0
    except FileNotFoundError:
        console.print("  [red]❌ Ollama CLI not found. Install from https://ollama.com[/red]")
        return False
    except subprocess.TimeoutExpired:
        console.print("  [red]❌ Pull timed out after 30 minutes.[/red]")
        return False
    except Exception as e:
        console.print(f"  [red]❌ Pull failed: {e}[/red]")
        return False


# Cloud pullable models
OLLAMA_CLOUD_MODELS = [
    {"name": "deepseek-v3.2:cloud", "label": "DeepSeek V3.2 - Reasoning+"},
    {"name": "qwen3.5:397b-cloud", "label": "Qwen 3.5 397B - General"},
    {"name": "qwen3-coder:480b-cloud", "label": "Qwen3 Coder 480B - Coding"},
    {"name": "kimi-k2.6:cloud", "label": "Kimi K2.6 - Multimodal Agentic"},
    {"name": "glm-5.1:cloud", "label": "GLM 5.1 - Agentic Engineering"},
    {"name": "nemotron-3-super:cloud", "label": "NVIDIA Nemotron Super 120B"},
    {"name": "gemma4:31b-cloud", "label": "Gemma 4 31B - Vision+Audio"},
    {"name": "gemini-3-flash-preview:cloud", "label": "Gemini 3 Flash - Vision"},
    {"name": "minimax-m2.7:cloud", "label": "MiniMax M2.7 - Latest"},
    {"name": "devstral-2:123b-cloud", "label": "Devstral 2 123B - Tool Use"},
]

OLLAMA_LOCAL_MODELS = [
    {"name": "codegemma:7b", "label": "Fast Coding 7B"},
    {"name": "qwen2.5-coder:3b", "label": "Light Coding"},
    {"name": "starcoder2:3b", "label": "Code Specialist"},
    {"name": "phi3:mini", "label": "Fastest"},
    {"name": "tinyllama:latest", "label": "Ultra Fast"},
    {"name": "moondream:latest", "label": "Vision"},
    {"name": "qwen3-vl:2b", "label": "Vision Light"},
]

OLLAMA_UNCENSORED_MODELS = [
    {"name": "dolphin-phi:latest", "label": "Uncensored Phi"},
    {"name": "dolphin-mistral:latest", "label": "Uncensored Mistral"},
    {"name": "dolphin-llama3:latest", "label": "Uncensored Llama3"},
    {"name": "wizard-vicuna-uncensored:latest", "label": "Uncensored Vicuna"},
    {"name": "nous-hermes:latest", "label": "Uncensored Hermes"},
    {"name": "openhermes:latest", "label": "Open Hermes"},
    {"name": "samantha-mistral:latest", "label": "Uncensored Samantha"},
    {"name": "mannix/llama3.1-8b-abliterated:latest", "label": "Uncensored Llama 3.1"},
]


def show_ollama_selection() -> dict[str, Any] | None:
    """Interactive Ollama model selection wizard."""
    console.print(Panel(
        "[bold rgb(0,230,110)]OLLAMA MODEL SELECTION[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")

    # Check Ollama status
    console.print("  [rgb(0,230,110)][*] Checking Ollama status...[/rgb(0,230,110)]")
    if not _ollama_is_running():
        console.print("  [yellow]⚠️  Ollama is not running.[/yellow]")
        console.print("  [dim]Trying to start Ollama...[/dim]")
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            import time
            for _ in range(10):
                time.sleep(1)
                if _ollama_is_running():
                    break
        except Exception:
            pass

        if not _ollama_is_running():
            console.print("  [red]❌ Ollama is not available. Install from https://ollama.com[/red]")
            console.print("  [dim]After installing, run 'ollama serve' and try again.[/dim]")
            Prompt.ask("\n  Press Enter to go back")
            return None

    console.print("  [green]✅ Ollama is running![/green]\n")

    # Detect specs
    specs = detect_and_display_specs()

    # Get installed models
    installed = _get_ollama_installed_models()
    installed_names = {m["name"] for m in installed}

    all_choices: list[dict[str, Any]] = []
    idx = 1

    # Installed models
    if installed:
        console.print(f"  [bold rgb(0,255,136)]━━━ YOUR INSTALLED MODELS ({len(installed)}) ━━━[/bold rgb(0,255,136)]")
        for m in installed:
            all_choices.append({"num": idx, "name": m["name"], "label": m["size"], "source": "installed"})
            console.print(f"    [rgb(80,255,160)][{idx:2d}][/rgb(80,255,160)] {m['name']:<40} {m['size']}")
            idx += 1
        console.print()

    # Cloud models (not already installed)
    cloud_not_installed = [c for c in OLLAMA_CLOUD_MODELS if c["name"] not in installed_names]
    if cloud_not_installed:
        console.print(f"  [bold rgb(0,200,90)]━━━ CLOUD MODELS (free — auto-pull) ━━━[/bold rgb(0,200,90)]")
        for c in cloud_not_installed:
            all_choices.append({"num": idx, "name": c["name"], "label": c["label"], "source": "cloud"})
            console.print(f"    [rgb(80,255,160)][{idx:2d}][/rgb(80,255,160)] {c['name']:<35} [{c['label']}]")
            idx += 1
        console.print()

    # Local pullable
    local_not_installed = [c for c in OLLAMA_LOCAL_MODELS if c["name"] not in installed_names]
    if local_not_installed:
        console.print(f"  [bold rgb(30,160,70)]━━━ LOCAL MODELS (auto-pull) ━━━[/bold rgb(30,160,70)]")
        for c in local_not_installed:
            all_choices.append({"num": idx, "name": c["name"], "label": c["label"], "source": "local"})
            console.print(f"    [rgb(80,255,160)][{idx:2d}][/rgb(80,255,160)] {c['name']:<35} [{c['label']}]")
            idx += 1
        console.print()

    # Uncensored
    uncensored_not_installed = [c for c in OLLAMA_UNCENSORED_MODELS if c["name"] not in installed_names]
    if uncensored_not_installed:
        console.print(f"  [bold rgb(20,120,50)]━━━ UNCENSORED MODELS (auto-pull) ━━━[/bold rgb(20,120,50)]")
        for c in uncensored_not_installed:
            all_choices.append({"num": idx, "name": c["name"], "label": c["label"], "source": "uncensored"})
            console.print(f"    [rgb(80,255,160)][{idx:2d}][/rgb(80,255,160)] {c['name']:<35} [{c['label']}]")
            idx += 1
        console.print()

    manual_num = idx
    console.print(f"  [bold white]━━━ OTHER ━━━[/bold white]")
    console.print(f"    [rgb(80,255,160)][{manual_num:2d}][/rgb(80,255,160)] Type model name manually (auto-pull)")
    console.print(f"    [rgb(80,255,160)][ 0][/rgb(80,255,160)] Back to main menu")
    console.print()

    choice = Prompt.ask(f"  Select [0-{manual_num}]", default="0")

    if choice == "0":
        return None

    choice_num = 0
    try:
        choice_num = int(choice)
    except ValueError:
        console.print("  [red]❌ Invalid selection![/red]")
        return show_ollama_selection()

    # Manual entry
    if choice_num == manual_num:
        model_name = Prompt.ask("  Model name", default="")
        if not model_name:
            return show_ollama_selection()
        if model_name not in installed_names and "-cloud" not in model_name:
            success = _ollama_pull_model(model_name)
            if not success:
                if not Confirm.ask("  Continue anyway?", default=False):
                    return show_ollama_selection()
        return {
            "id": "ollama", "provider": "ollama", "model": model_name,
            "api_key": "ollama", "api_base": "http://localhost:11434",
        }

    # Find in list
    selected = next((c for c in all_choices if c["num"] == choice_num), None)
    if not selected:
        console.print("  [red]❌ Invalid selection![/red]")
        return show_ollama_selection()

    # Auto-pull if not installed and not cloud
    if selected["source"] != "installed" and "-cloud" not in selected["name"]:
        if Confirm.ask(f"  Model '{selected['name']}' not installed. Auto-pull now?", default=True):
            success = _ollama_pull_model(selected["name"])
            if not success:
                console.print("  [yellow]⚠️  Will try to use anyway on first access.[/yellow]")

    console.print(f"\n  [bold rgb(0,255,136)]✅ Selected: {selected['name']}[/bold rgb(0,255,136)]")
    return {
        "id": "ollama", "provider": "ollama", "model": selected["name"],
        "api_key": "ollama", "api_base": "http://localhost:11434",
    }


# ═══════════════════════════════════════════════════════════════════════
#  SECTION 4: API KEY VALIDATION
# ═══════════════════════════════════════════════════════════════════════

def _test_api_key(provider: str, api_key: str) -> tuple[bool, str]:
    """Test an API key by hitting the provider's model list endpoint."""
    test_configs: dict[str, tuple[str, dict[str, str]]] = {
        "openai": (
            "https://api.openai.com/v1/models",
            {"Authorization": f"Bearer {api_key}"},
        ),
        "anthropic": (
            "https://api.anthropic.com/v1/models",
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        ),
        "gemini": (
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            {},
        ),
        "groq": (
            "https://api.groq.com/openai/v1/models",
            {"Authorization": f"Bearer {api_key}"},
        ),
        "openrouter": (
            "https://openrouter.ai/api/v1/models",
            {"Authorization": f"Bearer {api_key}"},
        ),
        "nvidia_nim": (
            "https://integrate.api.nvidia.com/v1/models",
            {"Authorization": f"Bearer {api_key}"},
        ),
        "deepseek": (
            "https://api.deepseek.com/v1/models",
            {"Authorization": f"Bearer {api_key}"},
        ),
    }

    if provider not in test_configs:
        return True, "No test endpoint available — assuming valid."

    url, headers = test_configs[provider]
    try:
        req = Request(url, method="GET")
        for k, v in headers.items():
            req.add_header(k, v)
        with urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True, "✅ Key is VALID! Connection successful."
            return False, f"❌ Key test FAILED! Status: {resp.status}"
    except URLError as e:
        return False, f"❌ Connection failed: {e.reason}"
    except Exception as e:
        return False, f"❌ Connection failed: {e}"


def prompt_and_validate_key(provider_id: str, provider_label: str, key_url_hint: str) -> str | None:
    """Prompt for an API key with optional instant validation."""
    console.print(f"  [dim]Get your key from: {key_url_hint}[/dim]")
    api_key = Prompt.ask(f"  Enter {provider_label} API Key", password=True, default="")
    if not api_key.strip():
        console.print("  [red]❌ API key is required.[/red]")
        return None

    api_key = api_key.strip()

    if Confirm.ask("  🔑 Test API key now?", default=True):
        console.print("  [dim]Testing connection...[/dim]")
        valid, message = _test_api_key(provider_id, api_key)
        if valid:
            console.print(f"  [green]{message}[/green]")
        else:
            console.print(f"  [red]{message}[/red]")
            if not Confirm.ask("  Continue with this key anyway?", default=False):
                return None

    console.print(f"  [green]✅ Key saved![/green]\n")
    return api_key


# ═══════════════════════════════════════════════════════════════════════
#  SECTION 5: CLOUD PROVIDER MENUS
# ═══════════════════════════════════════════════════════════════════════

def _show_model_menu(title: str, categories: list[dict[str, Any]], provider_id: str,
                     provider_name: str, api_key: str,
                     api_base: str | None = None) -> dict[str, Any] | None:
    """Generic model menu renderer for cloud providers."""
    console.print(Panel(
        f"[bold rgb(0,230,110)]{title}[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")
    console.print()

    all_models: dict[str, str] = {}
    idx = 1
    for cat in categories:
        console.print(f"  [bold rgb(0,200,90)][{cat['category']}][/bold rgb(0,200,90)]")
        for model_entry in cat["models"]:
            all_models[str(idx)] = model_entry["id"]
            tag = model_entry.get("tag", "")
            console.print(f"    [rgb(80,255,160)][{idx:2d}][/rgb(80,255,160)] {model_entry['id']:<42} [{tag}]")
            idx += 1
        console.print()

    custom_num = idx
    console.print(f"    [rgb(80,255,160)][{custom_num:2d}][/rgb(80,255,160)] Custom model name")
    console.print(f"    [rgb(80,255,160)][ 0][/rgb(80,255,160)] Back")
    console.print()

    choice = Prompt.ask(f"  Select [0-{custom_num}]", default="0")
    if choice == "0":
        return None

    if choice == str(custom_num):
        model = Prompt.ask("  Enter custom model name", default="")
        if not model:
            return None
    elif choice in all_models:
        model = all_models[choice]
    else:
        console.print("  [red]❌ Invalid selection![/red]")
        return None

    console.print(f"\n  [bold rgb(0,255,136)]✅ Selected: {model}[/bold rgb(0,255,136)]")

    result = {
        "id": provider_id, "provider": provider_name,
        "model": model, "api_key": api_key,
    }
    if api_base:
        result["api_base"] = api_base
    return result


# ── Google Antigravity / Gemini ────────────────────────────────────────

def show_gemini_selection() -> dict[str, Any] | None:
    """Google Antigravity / Gemini model selection."""
    console.print(Panel(
        "[bold rgb(0,230,110)]🚀 GOOGLE GEMINI / ANTIGRAVITY[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")

    api_key = prompt_and_validate_key("gemini", "Google", "https://aistudio.google.com/app/apikey")
    if not api_key:
        return None

    return _show_model_menu("🚀 GOOGLE GEMINI MODELS", [
        {"category": "GEMINI 2.5 — Latest (2025)", "models": [
            {"id": "gemini-2.5-pro", "tag": "Best Overall"},
            {"id": "gemini-2.5-flash", "tag": "Fastest"},
            {"id": "gemini-2.5-flash-lite", "tag": "Light"},
        ]},
        {"category": "GEMINI 3.1 — Preview", "models": [
            {"id": "gemini-3.1-pro-preview", "tag": "3.1 Pro"},
            {"id": "gemini-3.1-flash-lite-preview", "tag": "3.1 Lite"},
        ]},
        {"category": "GEMINI 3.0 — Preview", "models": [
            {"id": "gemini-3-pro-preview", "tag": "3.0 Pro"},
            {"id": "gemini-3-flash-preview", "tag": "3.0 Flash — Recommended"},
        ]},
        {"category": "GEMINI 2.0 — Stable", "models": [
            {"id": "gemini-2.0-flash", "tag": "Stable Flash"},
            {"id": "gemini-2.0-flash-lite", "tag": "Lite"},
        ]},
        {"category": "GEMMA — Open", "models": [
            {"id": "gemma-4-31b-it", "tag": "Gemma 4 31B"},
            {"id": "gemma-3-27b-it", "tag": "Gemma 3 27B"},
            {"id": "gemma-3-12b-it", "tag": "Gemma 3 12B"},
            {"id": "gemma-3-4b-it", "tag": "Gemma 3 4B"},
        ]},
    ], "gemini", "gemini", api_key,
       api_base="https://generativelanguage.googleapis.com/v1beta/openai")


# ── OpenAI / Codex ────────────────────────────────────────────────────

def show_openai_selection() -> dict[str, Any] | None:
    """OpenAI / Codex model selection."""
    console.print(Panel(
        "[bold rgb(0,230,110)]🔮 OPENAI / CODEX MODELS[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")

    api_key = prompt_and_validate_key("openai", "OpenAI", "https://platform.openai.com/api-keys")
    if not api_key:
        return None

    return _show_model_menu("🔮 OPENAI MODELS", [
        {"category": "O-SERIES — Reasoning", "models": [
            {"id": "o3", "tag": "Advanced Reasoning"},
            {"id": "o3-mini", "tag": "Fast Reasoning"},
            {"id": "o4-mini", "tag": "Mini Reasoning"},
        ]},
        {"category": "GPT-4.1 — Latest Coding", "models": [
            {"id": "gpt-4.1", "tag": "Best for Coding"},
            {"id": "gpt-4.1-mini", "tag": "Fast Coding"},
            {"id": "gpt-4.1-nano", "tag": "Ultra Fast"},
        ]},
        {"category": "GPT-4O — Vision", "models": [
            {"id": "gpt-4o", "tag": "Best with Vision"},
            {"id": "gpt-4o-mini", "tag": "Fast with Vision"},
        ]},
    ], "openai", "openai", api_key)


# ── Anthropic Claude ──────────────────────────────────────────────────

def show_anthropic_selection() -> dict[str, Any] | None:
    """Anthropic Claude model selection."""
    console.print(Panel(
        "[bold rgb(0,230,110)]🧠 ANTHROPIC CLAUDE[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")

    api_key = prompt_and_validate_key("anthropic", "Anthropic", "https://console.anthropic.com/settings/keys")
    if not api_key:
        return None

    return _show_model_menu("🧠 ANTHROPIC CLAUDE MODELS", [
        {"category": "CLAUDE 4 — Latest", "models": [
            {"id": "claude-4-opus", "tag": "Best Claude"},
            {"id": "claude-4-sonnet", "tag": "Fast Claude"},
        ]},
        {"category": "CLAUDE 3.5 — Stable", "models": [
            {"id": "claude-3-5-sonnet-20241022", "tag": "Claude 3.5 Sonnet"},
            {"id": "claude-3-5-haiku-20241022", "tag": "Claude 3.5 Haiku"},
        ]},
        {"category": "CLAUDE 3 — Legacy", "models": [
            {"id": "claude-3-opus-20240229", "tag": "Most Capable"},
            {"id": "claude-3-haiku-20240307", "tag": "Fastest"},
        ]},
    ], "anthropic", "anthropic", api_key, api_base="https://api.anthropic.com")


# ── Groq ──────────────────────────────────────────────────────────────

def show_groq_selection() -> dict[str, Any] | None:
    """Groq ultra-fast inference selection."""
    console.print(Panel(
        "[bold rgb(0,230,110)]⚡ GROQ — Ultra-Fast Inference[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")

    api_key = prompt_and_validate_key("groq", "Groq", "https://console.groq.com/")
    if not api_key:
        return None

    return _show_model_menu("⚡ GROQ MODELS (Verified Working)", [
        {"category": "LLAMA — Meta", "models": [
            {"id": "llama-3.3-70b-versatile", "tag": "Best — Recommended"},
            {"id": "llama-3.1-8b-instant", "tag": "8B — Ultra Fast"},
            {"id": "meta-llama/llama-4-scout-17b-16e-instruct", "tag": "Llama 4 Scout"},
        ]},
        {"category": "REASONING — DeepSeek", "models": [
            {"id": "deepseek-r1-distill-llama-70b", "tag": "DeepSeek R1 — Best"},
        ]},
        {"category": "QWEN — Alibaba", "models": [
            {"id": "qwen-qwq-32b", "tag": "QwQ 32B — Reasoning"},
        ]},
        {"category": "GEMMA — Google", "models": [
            {"id": "gemma2-9b-it", "tag": "Gemma 2 9B"},
        ]},
        {"category": "COMPOUND — Smart Routing", "models": [
            {"id": "compound-beta", "tag": "Smart Routing"},
            {"id": "compound-beta-mini", "tag": "Smart Routing Mini"},
        ]},
    ], "groq", "groq", api_key, api_base="https://api.groq.com/openai/v1")


# ── OpenRouter ────────────────────────────────────────────────────────

def show_openrouter_selection() -> dict[str, Any] | None:
    """OpenRouter 100+ models selection."""
    console.print(Panel(
        "[bold rgb(0,230,110)]🌐 OPENROUTER — 100+ Models[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")

    api_key = prompt_and_validate_key("openrouter", "OpenRouter", "https://openrouter.ai/")
    if not api_key:
        return None

    return _show_model_menu("🌐 OPENROUTER MODELS", [
        {"category": "CLAUDE — Anthropic", "models": [
            {"id": "anthropic/claude-4-sonnet", "tag": "Fast Claude"},
            {"id": "anthropic/claude-3.5-sonnet", "tag": "Claude 3.5"},
            {"id": "anthropic/claude-3-haiku", "tag": "Fastest"},
        ]},
        {"category": "GPT — OpenAI", "models": [
            {"id": "openai/gpt-4o", "tag": "GPT 4o"},
            {"id": "openai/gpt-4o-mini", "tag": "GPT 4o Mini"},
        ]},
        {"category": "LLAMA — Meta", "models": [
            {"id": "meta/llama-3.3-70b-instruct", "tag": "70B New"},
            {"id": "meta/llama-3.1-8b-instruct", "tag": "8B — Fast"},
        ]},
        {"category": "GEMINI — Google", "models": [
            {"id": "google/gemini-2.5-pro", "tag": "Gemini 2.5 Pro"},
            {"id": "google/gemini-2.5-flash", "tag": "Gemini 2.5 Flash"},
        ]},
        {"category": "DEEPSEEK — Reasoning", "models": [
            {"id": "deepseek/deepseek-chat", "tag": "Chat"},
            {"id": "deepseek/deepseek-coder", "tag": "Coder"},
        ]},
        {"category": "FREE TIER — Best Free", "models": [
            {"id": "google/gemma-2-9b-it", "tag": "Gemma 2 9B — Free"},
            {"id": "microsoft/phi-4-mini-instruct", "tag": "Phi-4 Mini — Free"},
        ]},
    ], "openrouter", "openrouter", api_key, api_base="https://openrouter.ai/api/v1")


# ── NVIDIA NIM ────────────────────────────────────────────────────────

def show_nvidia_selection() -> dict[str, Any] | None:
    """NVIDIA AI / NIM model selection."""
    console.print(Panel(
        "[bold rgb(0,230,110)]🎮 NVIDIA AI / NIM[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")

    api_key = prompt_and_validate_key("nvidia_nim", "NVIDIA", "https://build.nvidia.com/")
    if not api_key:
        return None

    return _show_model_menu("🎮 NVIDIA AI MODELS", [
        {"category": "LLAMA — Meta", "models": [
            {"id": "meta/llama-3.3-70b-instruct", "tag": "Best — Recommended"},
            {"id": "meta/llama-3.1-405b-instruct", "tag": "405B — Most Capable"},
            {"id": "meta/llama-3.1-8b-instruct", "tag": "8B — Fast"},
        ]},
        {"category": "QWEN — Alibaba", "models": [
            {"id": "qwen/qwen3.5-397b-a17b", "tag": "397B — Best Qwen"},
            {"id": "qwen/qwen2.5-coder-32b-instruct", "tag": "32B Coder"},
        ]},
        {"category": "DEEPSEEK — Reasoning", "models": [
            {"id": "deepseek-ai/deepseek-v4-pro", "tag": "v4 Pro"},
        ]},
        {"category": "GEMMA — Google", "models": [
            {"id": "google/gemma-4-31b-it", "tag": "Gemma 4"},
        ]},
    ], "nvidia", "nvidia_nim", api_key, api_base="https://integrate.api.nvidia.com/v1")


# ── DeepSeek ──────────────────────────────────────────────────────────

def show_deepseek_selection() -> dict[str, Any] | None:
    """DeepSeek model selection."""
    console.print(Panel(
        "[bold rgb(0,230,110)]🔬 DEEPSEEK — Reasoning[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")

    api_key = prompt_and_validate_key("deepseek", "DeepSeek", "https://platform.deepseek.com/api_keys")
    if not api_key:
        return None

    return _show_model_menu("🔬 DEEPSEEK MODELS", [
        {"category": "DEEPSEEK — Latest", "models": [
            {"id": "deepseek-chat", "tag": "General Chat — Recommended"},
            {"id": "deepseek-coder", "tag": "Coding Specialist"},
            {"id": "deepseek-reasoner", "tag": "Advanced Reasoning"},
        ]},
    ], "deepseek", "deepseek", api_key, api_base="https://api.deepseek.com")


# ═══════════════════════════════════════════════════════════════════════
#  SECTION 6: MAIN PROVIDER SELECTION MENU
# ═══════════════════════════════════════════════════════════════════════

PROVIDER_MENU = [
    ("1", "Ollama (Local)",       "Free — run models locally",          "ollama"),
    ("2", "Google Gemini",        "Gemini 2.5/3.0/3.1, Gemma 3/4",     "gemini"),
    ("3", "OpenAI / Codex",       "o3, gpt-4.1, gpt-4o",               "openai"),
    ("4", "Anthropic Claude",     "Claude 4/3.5 Sonnet/Opus",           "anthropic"),
    ("5", "Groq",                 "Ultra-fast inference — Free tier",    "groq"),
    ("6", "OpenRouter",           "100+ models — Free credits",         "openrouter"),
    ("7", "NVIDIA NIM",           "Llama, Qwen, DeepSeek on NVIDIA",   "nvidia"),
    ("8", "DeepSeek",             "Reasoning & Coding specialist",      "deepseek"),
]


def show_main_provider_menu() -> dict[str, Any] | None:
    """Show the main provider selection menu and dispatch to sub-menus."""
    console.print(Panel(
        "[bold rgb(0,230,110)]SELECT AI PROVIDER[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")
    console.print()

    table = Table(
        box=box.SIMPLE_HEAVY,
        border_style="rgb(0,180,80)",
        show_header=True,
        header_style="bold rgb(80,255,160)",
        pad_edge=True,
    )
    table.add_column("#", style="bold rgb(0,255,136)", width=4, justify="center")
    table.add_column("Provider", style="bold white", min_width=22)
    table.add_column("Description", style="rgb(120,255,180)", min_width=36)

    for num, name, desc, _ in PROVIDER_MENU:
        table.add_row(num, name, desc)

    console.print(table, justify="center")
    console.print()
    console.print("    [rgb(80,255,160)][ 0][/rgb(80,255,160)] Cancel / Back")
    console.print()

    choice = Prompt.ask("  Select provider [0-8]", default="0")

    dispatch: dict[str, Any] = {
        "1": show_ollama_selection,
        "2": show_gemini_selection,
        "3": show_openai_selection,
        "4": show_anthropic_selection,
        "5": show_groq_selection,
        "6": show_openrouter_selection,
        "7": show_nvidia_selection,
        "8": show_deepseek_selection,
    }

    handler = dispatch.get(choice)
    if handler:
        return handler()

    return None


# ═══════════════════════════════════════════════════════════════════════
#  SECTION 7: CONFIG SAVER (Safe YAML Merge)
# ═══════════════════════════════════════════════════════════════════════

def save_provider_to_config(workspace_path: Path, selection: dict[str, Any]) -> bool:
    """Safely merge the selected provider into config.user.yaml."""
    config_path = workspace_path / "config.user.yaml"

    # Load existing config (or start fresh)
    config_data: dict[str, Any] = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Build provider entry
    prov_entry: dict[str, Any] = {
        "id": selection["id"],
        "provider": selection["provider"],
        "model": selection["model"],
        "api_key": selection["api_key"],
        "priority": 1,
        "enabled": True,
    }
    if "api_base" in selection:
        prov_entry["api_base"] = selection["api_base"]

    # Update llm section
    if "llm" not in config_data:
        config_data["llm"] = {}

    config_data["llm"]["default_provider"] = selection["id"]

    # Update providers list
    providers = config_data["llm"].get("providers", [])
    # Disable all existing, update if same id exists
    found = False
    for prov in providers:
        prov["enabled"] = False
        if prov.get("id") == selection["id"]:
            prov.update(prov_entry)
            found = True
    if not found:
        providers.append(prov_entry)
    config_data["llm"]["providers"] = providers

    # Ensure default_agent exists
    if "default_agent" not in config_data:
        config_data["default_agent"] = "cyberclaw"

    try:
        with open(config_path, "w") as f:
            yaml.safe_dump(config_data, f, sort_keys=False, default_flow_style=False)
        return True
    except Exception as e:
        console.print(f"  [red]❌ Failed to save config: {e}[/red]")
        return False


# ═══════════════════════════════════════════════════════════════════════
#  SECTION 8: FULL MODEL SELECTION WIZARD (Entry Point)
# ═══════════════════════════════════════════════════════════════════════

def run_model_selection_wizard(workspace_path: Path, launch_chat_callback: Any = None) -> dict[str, Any] | None:
    """
    Run the full premium model selection wizard.

    Args:
        workspace_path: Path to the CyberClaw workspace.
        launch_chat_callback: Optional callable to launch chat after selection.
            Should accept (workspace_path,) as argument.

    Returns:
        The selected provider dict, or None if cancelled.
    """
    # Print banner
    print_cyberclaw_banner()

    # Show specs
    console.print(Panel(
        "[bold rgb(0,230,110)]🖥️  SYSTEM DETECTION[/bold rgb(0,230,110)]",
        border_style="rgb(0,180,80)", expand=False,
    ), justify="center")
    detect_and_display_specs()

    # Provider selection
    selection = show_main_provider_menu()

    if selection is None:
        console.print("\n  [yellow]Model selection cancelled.[/yellow]\n")
        return None

    # Save to config
    console.print(f"\n  [rgb(0,230,110)]💾 Saving configuration to config.user.yaml...[/rgb(0,230,110)]")
    if save_provider_to_config(workspace_path, selection):
        console.print(f"  [green]✅ Configuration saved successfully![/green]")
        console.print(f"      Provider: [bold rgb(0,255,136)]{selection['id']}[/bold rgb(0,255,136)]")
        console.print(f"      Model:    [bold rgb(0,255,136)]{selection['model']}[/bold rgb(0,255,136)]")
    else:
        console.print("  [red]❌ Failed to save configuration.[/red]")
        return selection

    # Summary panel
    console.print()
    console.print(Panel(
        f"[bold rgb(0,255,136)]✅ MODEL CONFIGURED SUCCESSFULLY![/bold rgb(0,255,136)]\n\n"
        f"  Provider: [bold white]{selection['provider']}[/bold white]\n"
        f"  Model:    [bold white]{selection['model']}[/bold white]\n\n"
        f"[dim]You can change this anytime with: cyberclaw select-model[/dim]",
        title="[bold rgb(80,255,160)]CyberClaw Ready[/bold rgb(80,255,160)]",
        border_style="rgb(0,180,80)",
        expand=False,
    ), justify="center")

    # Auto-launch chat option
    console.print()
    if Confirm.ask("  🚀 Would you like to start the Chat Session in terminal now?", default=True):
        if launch_chat_callback:
            launch_chat_callback(workspace_path)
        else:
            console.print("\n  [dim]Starting chat... Run [cyan]cyberclaw chat[/cyan] manually if needed.[/dim]")
    else:
        console.print("\n  [dim]You can start chatting anytime with: [cyan]cyberclaw chat[/cyan][/dim]")

    return selection
