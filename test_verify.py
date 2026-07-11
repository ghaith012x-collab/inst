from playwright.sync_api import sync_playwright
import time

p = sync_playwright().start()
browser = p.chromium.launch(
    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    headless=True,
)
page = browser.new_page(
    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
)
page.goto('https://www.instagram.com/accounts/emailsignup/', timeout=30000, wait_until='domcontentloaded')
time.sleep(3)

# Fill and submit quickly
inputs = page.locator('input:visible')
inputs.nth(0).fill('testuser999999@gmail.com')
for i in range(inputs.count()):
    if inputs.nth(i).get_attribute('type') == 'password':
        inputs.nth(i).fill('StrongPass123!')
        break
text_count = 0
for i in range(inputs.count()):
    if inputs.nth(i).get_attribute('type') == 'text' and text_count == 1:
        inputs.nth(i).fill('Alex Johnson')
        break
    elif inputs.nth(i).get_attribute('type') == 'text':
        text_count += 1
for i in range(inputs.count()):
    if inputs.nth(i).get_attribute('type') == 'search':
        inputs.nth(i).fill('alexjohnson' + str(int(time.time())))
        break

# DOB
for label, val in [("Select Month", "June"), ("Select Day", "15"), ("Select Year", "1995")]:
    cb = page.locator(f'[role="combobox"][aria-label="{label}"]')
    if cb.count() > 0:
        cb.first.click(timeout=3000)
        time.sleep(0.3)
        page.keyboard.type(val, delay=30)
        time.sleep(0.2)
        page.keyboard.press('Enter')
        time.sleep(0.3)

# Submit
submit = page.locator('div[role="button"]:has-text("Submit")')
submit.first.click(timeout=5000)
print("Clicked Submit!")
time.sleep(8)

# Analyze the verification dialog
print("\n=== FULL VERIFICATION DIALOG ANALYSIS ===")
dialog = page.locator('[role="dialog"]')
if dialog.count() > 0:
    html = dialog.first.evaluate('el => el.outerHTML')
    print(html[:3000])
    
    # Check for any input fields
    inputs_in_dialog = dialog.first.locator('input')
    print(f"\n\nInputs in dialog: {inputs_in_dialog.count()}")
    for i in range(inputs_in_dialog.count()):
        inp = inputs_in_dialog.nth(i)
        print(f"  Input {i}:")
        print(f"    Type: {inp.get_attribute('type')}")
        print(f"    Aria: {inp.get_attribute('aria-label')}")
        print(f"    Placeholder: {inp.get_attribute('placeholder')}")
        print(f"    Visible: {inp.is_visible()}")
    
    # Check for any buttons
    btns = dialog.first.locator('[role="button"]')
    print(f"\nButtons in dialog: {btns.count()}")
    for i in range(btns.count()):
        text = btns.nth(i).inner_text()[:50]
        disabled = btns.nth(i).get_attribute('aria-disabled') or 'false'
        visible = btns.nth(i).is_visible()
        print(f"  Button[{i}]: '{text}' disabled={disabled} visible={visible}")

# Also look for any code input fields on the page
print("\n=== Looking for code input fields ===")
code_inputs = page.locator('input[inputmode="numeric"], input[autocomplete="one-time-code"], input[placeholder*="code"], input[aria-label*="code"]')
print(f"Code inputs found: {code_inputs.count()}")

# Check body text for code-related keywords
body = page.locator('body').inner_text()
print("\n=== Body text keywords ===")
for kw in ['code', 'email', 'sent', 'check your', 'enter the', 'digit', 'confirm']:
    if kw.lower() in body.lower():
        print(f"  Found: '{kw}'")

browser.close()
p.stop()