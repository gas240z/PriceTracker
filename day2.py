import requests

products = []
WEBHOOK_URL = "http://localhost:5678/webhook/PriceBot-manual"


def add_product(name, url, current_price, target_price):
    new_product = {
        "name": name,
        "url": url,
        "current_price": current_price,
        "target_price": target_price,
        "previous_price": current_price,
    }
    products.append(new_product)

def remove_product(name):
    for product in products:
        if product["name"] == name:
            products.remove(product)
            break

def show_products():
    for i in products:
        print(f'Name: {i["name"]}, URL: {i["url"]}, Current Price: {i["current_price"]}, Target Price: {i["target_price"]}')

def is_price_dropped(product):
    return product["current_price"] <= product["target_price"]


def update_product_price(name, new_price):
    for product in products:
        if product["name"] == name:
            # Перед обновлением текущей цены сохраняем старую в previous_price
            product["previous_price"] = product["current_price"]
            product["current_price"] = new_price
            print(f"✅ '{name}' üçün yeni qiymət yazıldı: {new_price} (Köhnə: {product['previous_price']})")
            return True
    print("⚠️ Belə məhsul tapılmadı!")
    return False


def check_all_prices():
    discounted_products = []
    
    if not products:
        print("⚠️ Siyahıda məhsul yoxdur!")
        return

    print("⏳ Qiymətlər yoxlanılır...")

    for i in products:
        try:
            new_price = float(input(f"'{i['name']}' üçün saytdakı yeni qiyməti daxil edin: "))
        except ValueError:
            print("❌ Yanlış qiymət daxil edildi!")
            continue

        # 2. Сохраняем предыдущую цену и обновляем текущую
        prev = i.get("previous_price", i["current_price"])
        i["previous_price"] = i["current_price"]
        i["current_price"] = new_price

        current = i["current_price"]
        target = i["target_price"]
        
        # Условия проверки
        is_target_reached = current <= target
        is_price_dropped = current < prev
        
        if is_target_reached or is_price_dropped:
            print(f'🔥 Qiymət endi/düşdü: {i["name"]} (Cari: {current}, Əvvəlki: {prev})')
            discounted_products.append(i)
        else:
            print(f'ℹ️ {i["name"]}: Qiymət dəyişmədi və ya endirim olmadı.')
            
    # Отправка вебхука в n8n
    if discounted_products:
        payload = {"products": discounted_products}
        
        try:
            response = requests.post(WEBHOOK_URL, json=payload)
            if response.status_code == 200:
                print(f"✅ {len(discounted_products)} məhsul n8n-ə göndərildi!")
            else:
                print(f"⚠️ Xəta. Status kod: {response.status_code}")
        except Exception as e:
            print(f"❌ Webhook göndərilmədi: {e}")


def get_float_input(prompt):
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("Xeta: Xahis olunur ancaq reqem daxil edin!")

def get_int_input(prompt):
    while True:
        try:
            return int(input(prompt))
        except ValueError:
            print("Xeta: Xahis olunur ancaq reqem daxil edin!")


