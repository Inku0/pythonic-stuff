def lugemise_aeg(lk_arv: int, kirjasuurus: str) -> int:
    if kirjasuurus == "suur":
        lugemiskiirus = 20
    elif kirjasuurus == "keskmine":
        lugemiskiirus = 30
    elif kirjasuurus == "vaike":
        lugemiskiirus = 40
    else:
        print("Vale sisend")
        return None
    return lk_arv * lugemiskiirus

def main():
    faili_nimi = input("Sisesta faili nimi: ")
    try:
        with open(faili_nimi, "r") as fail:
            kokku_aeg = 0
            raamatud = [rida.strip() for rida in fail.readlines()]
            for raamat in raamatud:
                kaua_laheb = input(f"Raamatus on {raamat} lehekulge, kui suur on kirjastiil? ")
                kokku_aeg += lugemise_aeg(int(raamat), kaua_laheb)
        vormistatud_aeg = f"{kokku_aeg // 3600} tundi, {kokku_aeg % 3600 // 60} minutit, {kokku_aeg % 60} sekundit"
        print(f"kokku kulub lugemiseks {vormistatud_aeg}")
    except FileNotFoundError:
        print(f"Faili {faili_nimi} ei leitud.")
        exit(1)

main()