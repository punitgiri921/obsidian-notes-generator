"""
YouTube → Obsidian Notes Generator

Entry point — validates environment and launches the GUI.

Usage:
    python main.py

    Or double-click main.py on Windows.
"""

import sys
from pathlib import Path

# Ensure the project root is in the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv


def check_environment() -> list[str]:
    """
    Validate that all required environment variables are set.

    Returns:
        List of error messages, empty if everything is OK.
    """

    import os

    load_dotenv(project_root / '.env')

    errors = []

    required_vars = [
        'AZURE_OPENAI_ENDPOINT',
        'AZURE_OPENAI_KEY',
        'AZURE_OPENAI_DEPLOYMENT',
    ]

    for var in required_vars:
        if not os.getenv(var):
            errors.append(f"Missing environment variable: {var}")

    return errors


def main():
    """Validate environment, then launch the GUI."""

    errors = check_environment()

    if errors:
        print("\n❌ Configuration Error:")
        print("─" * 40)

        for error in errors:
            print(f"  • {error}")

        print("\nPlease configure your .env file with:")
        print("  AZURE_OPENAI_ENDPOINT=https://...")
        print("  AZURE_OPENAI_KEY=your-api-key")
        print("  AZURE_OPENAI_DEPLOYMENT=your-model-name")
        print("  AZURE_OPENAI_API_VERSION=2024-10-21")

        input("\nPress Enter to exit...")
        return

    # Import and launch the GUI
    from gui.app import App

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
