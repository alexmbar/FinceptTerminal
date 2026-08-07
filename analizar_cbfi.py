#!/usr/bin/env python3
"""
Analizador de CBFI para GBM México
===================================
Script práctico para valuar y analizar Certificados Bursátiles Fiduciarios

Uso:
    python3 analizar_cbfi.py
"""

import sys
from datetime import datetime
from dataclasses import dataclass
import math

@dataclass
class CBFI:
    """Modelo de datos para CBFI"""
    nombre: str
    valor_nominal: float      # Normalmente $1,000
    tasa_cupon: float        # Ej: 0.065 = 6.5%
    plazo_years: float       # Años al vencimiento
    precio_mercado: float    # Precio actual en pesos
    frecuencia_cupones: int  # Pagos por año (2 = semestral)


class AnalizadorCBFI:
    """Calculadora profesional de CBFI"""

    def __init__(self, cbfi: CBFI):
        self.cbfi = cbfi

    def calcular_ytm(self) -> float:
        """Calcula Yield to Maturity (YTM) - tasa de retorno anual"""
        # Aproximación usando Newton-Raphson
        ytm = self.cbfi.tasa_cupon  # Estimación inicial

        for _ in range(100):  # Iteraciones
            pv = self._precio_presente(ytm)
            dpv = self._derivada_precio(ytm)

            ytm_nuevo = ytm - (pv - self.cbfi.precio_mercado) / dpv

            if abs(ytm_nuevo - ytm) < 0.00001:
                break
            ytm = ytm_nuevo

        return ytm

    def _precio_presente(self, ytm: float) -> float:
        """Calcula el precio presente dado un YTM"""
        periodos = int(self.cbfi.plazo_years * self.cbfi.frecuencia_cupones)
        tasa_periodo = ytm / self.cbfi.frecuencia_cupones
        cupones = self.cbfi.valor_nominal * self.cbfi.tasa_cupon / self.cbfi.frecuencia_cupones

        pv = 0
        for t in range(1, periodos + 1):
            pv += cupones / ((1 + tasa_periodo) ** t)

        pv += self.cbfi.valor_nominal / ((1 + tasa_periodo) ** periodos)
        return pv

    def _derivada_precio(self, ytm: float) -> float:
        """Derivada del precio para cálculo de YTM"""
        h = 0.0001
        p_up = self._precio_presente(ytm + h)
        p_down = self._precio_presente(ytm - h)
        return (p_up - p_down) / (2 * h)

    def calcular_duration(self) -> dict:
        """Calcula Macaulay Duration y Modified Duration"""
        ytm = self.calcular_ytm()
        periodos = int(self.cbfi.plazo_years * self.cbfi.frecuencia_cupones)
        tasa_periodo = ytm / self.cbfi.frecuencia_cupones
        cupones = self.cbfi.valor_nominal * self.cbfi.tasa_cupon / self.cbfi.frecuencia_cupones

        # Weighted average time to cash flows
        suma_pv_t = 0
        suma_pv = 0

        for t in range(1, periodos + 1):
            flujo = cupones if t < periodos else cupones + self.cbfi.valor_nominal
            pv_flujo = flujo / ((1 + tasa_periodo) ** t)
            suma_pv_t += t * pv_flujo
            suma_pv += pv_flujo

        macaulay_duration = (suma_pv_t / suma_pv) / self.cbfi.frecuencia_cupones
        modified_duration = macaulay_duration / (1 + tasa_periodo)

        # DV01 = cambio de precio si tasa sube 1%
        dv01 = modified_duration * self.cbfi.precio_mercado * 0.01

        return {
            'macaulay': macaulay_duration,
            'modified': modified_duration,
            'dv01': dv01
        }

    def calcular_precio_justo(self, ytm: float = None) -> float:
        """Calcula el precio justo del CBFI"""
        if ytm is None:
            ytm = self.cbfi.tasa_cupon  # Usar cupón como estimación

        return self._precio_presente(ytm)

    def evaluar_compra(self) -> dict:
        """Evaluación integral: ¿es buen momento para comprar?"""
        ytm = self.calcular_ytm()
        duration = self.calcular_duration()
        precio_justo = self.calcular_precio_justo(ytm)

        # Criterios
        criterios = {
            'ytm_atractivo': ytm > 0.065,  # > 6.5%
            'duration_segura': duration['modified'] < 5,  # < 5 años
            'precio_favorable': self.cbfi.precio_mercado < precio_justo,
            'plazo_razonable': self.cbfi.plazo_years > 1 and self.cbfi.plazo_years < 10
        }

        # Contar criterios cumplidos
        criterios_cumplidos = sum(criterios.values())

        # Recomendación
        if criterios_cumplidos >= 3:
            recomendacion = "✅ COMPRAR"
        elif criterios_cumplidos == 2:
            recomendacion = "⚠️  ESPERAR"
        else:
            recomendacion = "❌ NO COMPRAR"

        return {
            'ytm': ytm,
            'precio_justo': precio_justo,
            'diferencia_precio': self.cbfi.precio_mercado - precio_justo,
            'duration': duration,
            'criterios': criterios,
            'recomendacion': recomendacion,
            'criterios_cumplidos': criterios_cumplidos
        }

    def mostrar_analisis(self):
        """Imprime análisis completo del CBFI"""
        resultado = self.evaluar_compra()

        print("\n" + "="*70)
        print(f"  ANÁLISIS DE {self.cbfi.nombre}".center(70))
        print("="*70)

        print(f"\n📊 CARACTERÍSTICAS DEL INSTRUMENTO:")
        print(f"  Valor Nominal:        ${self.cbfi.valor_nominal:,.2f}")
        print(f"  Precio Actual:        ${self.cbfi.precio_mercado:,.2f}")
        print(f"  Tasa de Cupón:        {self.cbfi.tasa_cupon*100:.2f}%")
        print(f"  Plazo al Vencimiento: {self.cbfi.plazo_years:.1f} años")
        print(f"  Frecuencia Cupones:   {self.cbfi.frecuencia_cupones}x al año")

        print(f"\n💰 VALUACIÓN:")
        print(f"  Precio Justo:         ${resultado['precio_justo']:,.2f}")
        print(f"  YTM (Rendimiento):    {resultado['ytm']*100:.3f}%")
        print(f"  Diferencia:           ${resultado['diferencia_precio']:,.2f}", end="")
        if resultado['diferencia_precio'] > 0:
            print(" (SOBREVALORADO)")
        else:
            print(" (SUBVALORADO)")

        print(f"\n📈 ANÁLISIS DE RIESGO:")
        print(f"  Duration Macaulay:    {resultado['duration']['macaulay']:.2f} años")
        print(f"  Duration Modificada:  {resultado['duration']['modified']:.2f} años")
        print(f"  DV01:                 ${resultado['duration']['dv01']:,.2f}")
        print(f"  Interpretación DV01:  Si suben tasas 1%, el precio cae ${resultado['duration']['dv01']:,.2f}")

        print(f"\n✅ CRITERIOS DE COMPRA:")
        for criterio, cumplido in resultado['criterios'].items():
            estado = "✓" if cumplido else "✗"
            print(f"  [{estado}] {criterio.replace('_', ' ').title()}")

        print(f"\n🎯 RECOMENDACIÓN: {resultado['recomendacion']}")
        print(f"  Criterios cumplidos: {resultado['criterios_cumplidos']}/4")

        print("\n" + "="*70 + "\n")


def main():
    """Función principal con ejemplos"""

    print("""
╔═══════════════════════════════════════════════════════════════════╗
║           ANALIZADOR DE CBFI - GBM MÉXICO v1.0                   ║
║                  Análisis de Renta Fija Profesional               ║
╚═══════════════════════════════════════════════════════════════════╝
    """)

    # Ejemplos de CBFI (datos ficticios para demostración)
    cbfis_ejemplo = [
        CBFI(
            nombre="CBFI4B",
            valor_nominal=1000,
            tasa_cupon=0.065,      # 6.5%
            plazo_years=5,
            precio_mercado=980,
            frecuencia_cupones=2
        ),
        CBFI(
            nombre="CBFI5B",
            valor_nominal=1000,
            tasa_cupon=0.075,      # 7.5%
            plazo_years=7,
            precio_mercado=1005,
            frecuencia_cupones=2
        ),
        CBFI(
            nombre="CBFI6B",
            valor_nominal=1000,
            tasa_cupon=0.055,      # 5.5%
            plazo_years=3,
            precio_mercado=995,
            frecuencia_cupones=2
        ),
    ]

    # Analizar cada CBFI
    for cbfi in cbfis_ejemplo:
        analizador = AnalizadorCBFI(cbfi)
        analizador.mostrar_analisis()

    # Tabla comparativa
    print("\n📋 TABLA COMPARATIVA:\n")
    print(f"{'CBFI':<10} {'Precio':<12} {'YTM':<10} {'Duration':<12} {'Recomendación':<20}")
    print("-" * 64)

    for cbfi in cbfis_ejemplo:
        analizador = AnalizadorCBFI(cbfi)
        resultado = analizador.evaluar_compra()
        print(
            f"{cbfi.nombre:<10} "
            f"${resultado['precio_justo']:<11,.0f} "
            f"{resultado['ytm']*100:<9.3f}% "
            f"{resultado['duration']['modified']:<11.2f} "
            f"{resultado['recomendacion']:<20}"
        )

    print("\n" + "="*70)
    print("💡 TIPS:")
    print("  • YTM > 7% → Rendimiento atractivo")
    print("  • Duration < 5 años → Riesgo de tasa controlado")
    print("  • Precio < Justo → Oportunidad de compra")
    print("  • DV01 bajo → Menos sensible a cambios de tasa")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
