def arvuta_pesa_kiirendus(branchiness: float, edukus_list: list[float]) -> float:
    karistus = 1.0  # üks tsükkel
    pesade_arv = len(edukus_list)

    # Vana CPI: kõik ajapesad ebaõnnestuvad
    cpi_vana = 1.0 + branchiness * (pesade_arv * karistus)

    # Uus CPI: ajapesad ebaõnnestuvad vastavalt edukusele
    kogu_karistus_uus = sum((1.0 - e) * karistus for e in edukus_list)
    cpi_uus = 1.0 + branchiness * kogu_karistus_uus

    if cpi_uus <= 0.0:
        return float("inf")

    return cpi_vana / cpi_uus


def _sisendid_kehtivad(branchiness: float, edukus_list: list[float]) -> bool:
    if not (0.0 <= branchiness <= 1.0):
        return False
    if not edukus_list:  # tühi loend
        return False
    if any(not (0.0 <= e <= 1.0) for e in edukus_list):
        return False
    return True


def pesakiirus() -> None:
    try:
        branchiness: float = float(
            input("sisesta hargnemise käskude osakaal (0..1, kümnendmurd): ")
        )
        toores_edukus_list: str = input(
            "sisesta ajapesade täitmiste edukused (tühikutega, 0..1): "
        )
        kena_edukus_list: list[float] = [
            float(edukus) for edukus in toores_edukus_list.split()
        ]
    except ValueError:
        print("Vigased sisendid.")
        return

    if not _sisendid_kehtivad(branchiness, kena_edukus_list):
        print("Vigased sisendid.")
        return

    vastus: float = arvuta_pesa_kiirendus(
        branchiness=branchiness, edukus_list=kena_edukus_list
    )
    print(f"{vastus:.3f}") if len(kena_edukus_list) > 1 else print(f"{vastus:.2f}")


if __name__ == "__main__":
    pesakiirus()
