import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))



def generate_discount_message(product_name, current_price, target_price):
    prompt = (
        f"The item '{product_name}' has dropped in price! We were waiting for {target_price}, "
        f"and now it costs {current_price}. Write a short, joyful, and emotional Telegram message "
        f"(maximum 2 sentences) in Russian to excite the user."
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are a helpful price tracking bot."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

if __name__ == "__main__":
    # Тестовый вызов функции
    test_message = generate_discount_message(
        product_name="PlayStation 5", 
        current_price=450.0, 
        target_price=500.0
    )
    print(test_message)

