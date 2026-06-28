import os

def get_installed_apps():
    apps = {}
    # 🔍 The 4 hidden places Windows stores your app shortcuts
    paths = [
        os.environ.get('PROGRAMDATA', '') + r'\Microsoft\Windows\Start Menu\Programs',
        os.environ.get('APPDATA', '') + r'\Microsoft\Windows\Start Menu\Programs',
        os.environ.get('USERPROFILE', '') + r'\Desktop',
        os.environ.get('USERPROFILE', '') + r'\OneDrive\Desktop' # Common on Win 11
    ]

    print("🔍 Scanning PC for installed applications...")
    for base_path in paths:
        if not os.path.exists(base_path):
            continue
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.endswith(".lnk"): # We only want shortcuts
                    # Clean up the name (e.g., "Discord.lnk" becomes "discord")
                    clean_name = os.path.splitext(file)[0].lower()
                    full_path = os.path.join(root, file)
                    apps[clean_name] = full_path

    print(f"✅ Found {len(apps)} applications!")
    return apps