# 1 acre = 0.4047 hektarit
def juurdekasv(kiirus: float, pindala:float) -> float:
    return kiirus*(0.4047*pindala)

def main():
    failinimi = input("Faili nimi: ")
    kiirus = float(input("Juurdekasv: "))
    piir = float(input("Piir: "))
    andmed = []

    with open(failinimi, "r") as failinimi:
        for anne in failinimi:
            val = float(anne)
            if val > piir:
                andmed.append(val)
                print(f"Aastane juurdekasv on {round(juurdekasv(kiirus, val), 2)}")
            else:
                print("Metsatükki ei võeta arvesse")
    print(f"Arvutati {len(andmed)} metsatüki juurdekasv.")

main()
