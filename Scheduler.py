# import time
# import schedule
# from birmarket_parser import parse_birmarket_product
# import requests
# import json

# # Ваш скрипт может периодически читать products.json и проверять цены
# def job():
#   print("Запуск ежедневной проверки цен...")
#   # Здесь логика чтения products.json, парсинга и отправки webhook

# # Календарь проверки (например, каждый день в 9:00 утра)
# schedule.every().day.at("09:00").do(job)

# while True:
#   schedule.run_pending()
#   time.sleep(1)