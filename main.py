import asyncio
from pathlib import Path

from kivy.core.text import LabelBase

from core.app import AsteroideaApp


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir / "GeistMono.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path("/system/fonts/RobotoMono-Regular.ttf"),
        Path("/system/fonts/DroidSansMono.ttf"),
        Path("/system/fonts/CutiveMono.ttf"),
    ]
    for p in candidates:
        if p.exists():
            LabelBase.register(name="AppMono", fn_regular=str(p))
            break
    else:
        LabelBase.register(name="AppMono", fn_regular="Roboto")

    app = AsteroideaApp(base_dir=base_dir)
    asyncio.run(app.app_main())


if __name__ == "__main__":
    main()
