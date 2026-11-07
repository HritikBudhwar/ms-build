"""Check that .env is filled in and both services answer.

    python scripts/check_setup.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from munshi import config  # noqa: E402
from munshi.llm import LLMError, chat_json  # noqa: E402
from munshi.memory import Memory  # noqa: E402

OK, BAD = "\033[32m✓\033[0m", "\033[31m✗\033[0m"


async def main():
    ok = True
    if not (config.ROOT / ".env").exists():
        print(f"{BAD} .env missing: cp .env.example .env and fill it in")
        return False

    mem = Memory()
    if not mem.enabled:
        print(f"{BAD} HINDSIGHT_API_KEY is empty (needed for {config.HINDSIGHT_URL})")
        ok = False
    else:
        try:
            await mem.ensure_bank()
            await mem.client.arecall(bank_id=mem.bank, query="setup check", budget="low")
            print(f"{OK} Hindsight reachable at {config.HINDSIGHT_URL}, bank '{mem.bank}' ready")
        except Exception as e:
            print(f"{BAD} Hindsight error: {e}")
            ok = False

    if not config.LLM_API_KEY:
        print(f"{BAD} LLM_API_KEY is empty (Groq keys: https://console.groq.com/keys)")
        ok = False
    else:
        try:
            r = await chat_json("Reply with JSON only.", 'Return {"ok": true}', attempts=1)
            print(f"{OK} LLM {config.LLM_MODEL} answered: {r}")
        except LLMError as e:
            print(f"{BAD} LLM error: {e}")
            ok = False

    await mem.client.aclose()
    print("\nAll good. Next: python scripts/replay_history.py" if ok else "\nFix the items above, then re-run.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
