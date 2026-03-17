import re

path = r"C:\Users\pnish\OneDrive\Desktop\BCA\Atles\place1\log_p.py"

with open(path, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

# Fix 1: hardcode DB password
old = 'password = st.secrets.get("DB_PASSWORD", ""),'
new = 'password = "my@123appsql892819",'
content = content.replace(old, new)

# Fix 2: fix check_pw to strip whitespace
old2 = 'def check_pw(pw, h): return bcrypt.checkpw(pw.encode(), h.encode())'
new2 = '''def check_pw(pw, h):
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), h.strip().encode("utf-8"))
    except Exception:
        return False'''
content = content.replace(old2, new2)

# Fix 3: fix otp leak
content = content.replace(
    'st.session_state.otp         = "my@123appsql892819"',
    'st.session_state.otp         = ""'
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("=" * 50)
print("DONE! log_p.py has been patched.")
if "my@123appsql892819" in content:
    print("OK  DB password is hardcoded.")
else:
    print("WARN  DB password line not found - may already be set.")
print("=" * 50)
print("Now restart Streamlit and try login again.")
input("Press Enter to close...")
