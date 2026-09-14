"""Local PDF receipt ("boleta") generation with fpdf2 (Fase 5).

Unlike resend_client.py / cloudinary_client.py, this has no third-party
credential or dev-fallback contract to worry about: fpdf2 is a local
library, not a hosted API, so it always genuinely generates the file on
disk — there is no "real" vs "simulated" mode here. Always called from a
BackgroundTasks callback after checkout (see order_service.py), never
inside the request/response cycle, so a slow render never delays the
checkout response.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from app.models import Order, OrderItem, User

# Carpeta donde se guardan las boletas generadas — igual que outbox/ y
# media/, esta en .gitignore: son archivos generados, no codigo fuente.
_RECEIPTS_DIR = Path("receipts")


def generate_receipt_pdf(*, order: Order, items: list[OrderItem], user: User) -> Path:
    """Renders the boleta for one order and saves it as
    receipts/<order_code>.pdf, overwriting any previous attempt for the
    same order (checkout only ever calls this once per order, but a retry
    of the background task itself should stay idempotent too).
    """
    # mkdir(parents=True, exist_ok=True): crea la carpeta si no existe
    # todavia (primer PDF generado en el ambiente) sin fallar si ya estaba.
    _RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _RECEIPTS_DIR / f"{order.order_code}.pdf"

    pdf = FPDF()
    pdf.add_page()

    # Titulo del documento.
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "GameVault UCN - Boleta de compra", new_x="LMARGIN", new_y="NEXT")

    # Datos generales de la orden: codigo, cliente y fecha de pago.
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Orden: {order.order_code}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Cliente: {user.full_name} ({user.email})", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Fecha de pago: {order.paid_at.isoformat()}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Encabezado de la tabla de items (columnas con ancho fijo, con borde).
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(90, 8, "Juego", border=1)
    pdf.cell(30, 8, "Precio base", border=1)
    pdf.cell(25, 8, "Desc.", border=1)
    pdf.cell(35, 8, "Precio final", border=1, new_x="LMARGIN", new_y="NEXT")

    # Una fila por cada juego comprado, usando los valores CONGELADOS del
    # OrderItem (title_snapshot, no el titulo actual del Game).
    pdf.set_font("Helvetica", "", 11)
    for item in items:
        pdf.cell(90, 8, item.title_snapshot[:48], border=1)
        pdf.cell(30, 8, f"${item.unit_price}", border=1)
        pdf.cell(25, 8, f"{item.discount_percent}%", border=1)
        pdf.cell(35, 8, f"${item.final_price}", border=1, new_x="LMARGIN", new_y="NEXT")

    # Totales finales de la orden.
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, f"Subtotal: ${order.subtotal}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Descuento: -${order.discount_total}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Total pagado: ${order.total}", new_x="LMARGIN", new_y="NEXT")

    # output(str(path)) escribe el PDF a disco en la ruta indicada.
    pdf.output(str(path))
    return path
