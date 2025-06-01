def parandatud_tulemus(vigane_tulemus: float, mooteparandus: int) -> float:
    # m, cm
    return vigane_tulemus + (mooteparandus / 100) # sentimeetriteks

def main():
    failinimi = input("Failinimi: ")
    mooteparandus = int(input("Mooteparandus (cm): "))
    normatiiv = float(input("Normatiiv (m): "))

    uju_tolerants = 1e-4

    with open(failinimi, "r") as fail:
        parandatud_jarjend = [round(parandatud_tulemus(float(rida), mooteparandus), 2) for rida in fail.readlines()]
        print("Tegelikud tulemused")
        for tulemus in parandatud_jarjend:
            print(tulemus)
        normatiivi_taitnud = [taitnud for taitnud in parandatud_jarjend if taitnud >= normatiiv or (abs(taitnud - normatiiv) < uju_tolerants)]
        print(f"Normatiivi täitsid {len(normatiivi_taitnud)}")
        print(f"Keskmine tulemus: {round(sum(normatiivi_taitnud) / len(normatiivi_taitnud), 2)}")

main()
