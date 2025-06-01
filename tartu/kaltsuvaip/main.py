# algpikkus lõpust 20% suurem
# + 50cm kokku varu

def loimede_pikkus(lopp_pikkus: float, loimed: int) -> float:
    return round(lopp_pikkus * loimed, 2)

def main():
    failinimi = input("Failinimi: ")
    pikk_loim_arv = int(input("kõrvuti olevate lõimede arv 5-meetriste ja pikemate vaipade puhul: "))
    luhike_loim_arv = int(input("kõrvuti olevate lõimede arvu lühemate vaipade puhul: "))
    arvutatud_pikkused = []
    with open(failinimi, "r") as fail:
        vaiba_pikkused = fail.readlines()
        for vaip in vaiba_pikkused:
            lopp_pikkus = float(vaip) * 1.2 + 0.5
            arvutatud_pikkused.append(loimede_pikkus(float(lopp_pikkus), pikk_loim_arv)) if float(vaip) >= 5.0 else arvutatud_pikkused.append(loimede_pikkus(float(lopp_pikkus), luhike_loim_arv))
    print(f" vaja läheb {sum(arvutatud_pikkused)} m lõimeniiti")

main()
