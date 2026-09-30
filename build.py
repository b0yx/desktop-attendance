import os
import platform
import shutil
import subprocess
import sys


def build():
    print("=" * 60)
    print(" SmartHR Attendance System — Standalone Build Script")
    print("=" * 60)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    # Clean previous build artifacts
    for folder in ["build", "dist"]:
        p = os.path.join(base_dir, folder)
        if os.path.exists(p):
            print(f"Cleaning {folder}/...")
            shutil.rmtree(p)

    spec_file = os.path.join(base_dir, "SmartHR_Attendance.spec")
    if os.path.exists(spec_file):
        os.remove(spec_file)

    # Determine OS specific data separator
    is_win = platform.system() == "Windows"
    sep = ";" if is_win else ":"
    icon_path = os.path.join(base_dir, "assets", "app_icon.ico" if is_win else "app_icon.png")

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name=SmartHR_Attendance",
        f"--add-data=assets{sep}assets",
        "--hidden-import=customtkinter",
        "--hidden-import=PIL",
        "--hidden-import=PIL._imagingtk",
        "--hidden-import=PIL.ImageTk",
        "--hidden-import=openpyxl",
        "--hidden-import=pandas",
        "--hidden-import=sqlite3",
        "--collect-all=customtkinter",
    ]

    if os.path.exists(icon_path):
        pyinstaller_cmd.append(f"--icon={icon_path}")

    pyinstaller_cmd.append("main.py")

    print("\nRunning PyInstaller command:")
    print(" ".join(pyinstaller_cmd))
    print("-" * 60)

    result = subprocess.run(pyinstaller_cmd)
    if result.returncode == 0:
        dist_dir = os.path.join(base_dir, "dist")
        exe_name = "SmartHR_Attendance.exe" if is_win else "SmartHR_Attendance"
        out_file = os.path.join(dist_dir, exe_name)
        print("\n" + "=" * 60)
        print(" BUILD COMPLETE!")
        print(f" Output Binary: {out_file}")
        print("=" * 60)
    else:
        print("\n[ERROR] Compilation failed with return code:", result.returncode)
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
