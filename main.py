from day2 import check_all_prices, get_float_input, get_int_input, add_product, remove_product, show_products
from day3api import generate_discount_message

def main():
    while True:
        print('1. Mehsullari goster')
        print('2. Mehsul elave et')
        print('3. Mehsul sil')
        print('4. Cixis')
        print('5. Qiymetleri yoxla')

        choice = get_int_input('Seciminizi edin: ')
        
        if choice == 1:
            show_products()
        elif choice == 2:
            name = input("Meshulun adi: ")
            url = input("Link: ")
            current_price = get_float_input("Hal hazirdaki qiymet: ")
            target_price = get_float_input("Gozlenilen qiymet: ")
            add_product(name, url, current_price, target_price)
        elif choice == 3:
            name = input("Hansi mehsulu silmek isteyirsiz? ")
            remove_product(name)
        elif choice == 4:
            print("Sagolun!")
            break
        elif choice == 5:
            check_all_prices()
        else:
            print("Secim yalniz 1 den 5 e qeder ola biler")

if __name__ == "__main__":
    main()
