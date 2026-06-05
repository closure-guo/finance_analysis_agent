"""HF Spaces entry point — bridge to the real Gradio app."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from finance_agent.app import demo  # noqa: E402

if __name__ == "__main__":
    demo.launch()
