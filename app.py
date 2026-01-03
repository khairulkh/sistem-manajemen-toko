from flask import jsonify
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func
import pandas as pd

app = Flask(__name__)
app.secret_key = "luisindo_master_super_perfect_v22"

# DATABASE CONFIG
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/db_toko'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---
class Produk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    stok_lusin = db.Column(db.Integer, default=0)
    stok_pcs = db.Column(db.Integer, default=0)
    harga_grosir = db.Column(db.Integer, default=0)
    supplier = db.Column(db.String(100))
    tanggal_input = db.Column(db.DateTime, default=datetime.now)

class Penjualan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama_barang = db.Column(db.String(100))
    jumlah_ls = db.Column(db.Integer, default=0)
    jumlah_pcs = db.Column(db.Integer, default=0)
    total_omzet = db.Column(db.Integer, default=0)
    tanggal_transaksi = db.Column(db.DateTime, default=datetime.now)

class Pengeluaran(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama_pengeluaran = db.Column(db.String(200))
    jumlah_biaya = db.Column(db.Integer, default=0)
    tanggal = db.Column(db.DateTime, default=datetime.now)

with app.app_context():
    db.create_all()

# --- HELPER LOGIKA SUPPLIER ---
def get_supplier_from_form(form):
    opt = form.get('supplier_opt')
    if opt == "Custom":
        return form.get('supplier_custom', '').upper()
    return opt.upper() if opt else "-"

# --- ROUTES STOK ---
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    filter_supplier = request.args.get('supplier', '')
    # Pastikan variabel 'all' ditangkap di sini
    show_all = request.args.get('all', 'false') == 'true' 
    
    list_supplier = [s[0] for s in db.session.query(Produk.supplier).distinct().all() if s[0]]
    query = Produk.query
    
    if search: query = query.filter(Produk.nama.contains(search))
    if filter_supplier: query = query.filter(Produk.supplier == filter_supplier)
    
    # Logic Per Page: Jika 'show_all' true, tampilkan 10.000 data sekaligus
    per_page = 10000 if show_all else 20
    pagination = query.order_by(Produk.nama.asc()).paginate(page=page, per_page=per_page)
    
    return render_template('index.html', 
                           pagination=pagination, 
                           search=search, 
                           all_suppliers=list_supplier, 
                           filter_supplier=filter_supplier,
                           show_all=show_all) # Variabel ini wajib dikirim
@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    search = request.args.get('q', '').strip().lower()
    if not search:
        return jsonify([])
    
    # Mencari di data STOK BARANG
    # Gunakan limit 15 agar pilihan lebih banyak tapi tetap cepat
    results = Produk.query.filter(Produk.nama.ilike(f'%{search}%')).limit(15).all()
    
    suggestions = []
    for p in results:
        suggestions.append({
            'nama': p.nama.upper(),
            'harga': p.harga_grosir, # Ini harga modal/lusin
            'stok': f"{p.stok_lusin} LS {p.stok_pcs} PCS"
        })
        
    return jsonify(suggestions)

@app.route('/tambah_produk', methods=['GET', 'POST'])
def tambah_produk():
    if request.method == 'POST':
        db.session.add(Produk(
            nama=request.form.get('nama', '').upper(),
            stok_lusin=int(request.form.get('lusin') or 0),
            stok_pcs=int(request.form.get('pcs') or 0),
            harga_grosir=int(request.form.get('harga_grosir') or 0),
            supplier=get_supplier_from_form(request.form)
        ))
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('tambah.html')

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    p = Produk.query.get_or_404(id)
    if request.method == 'POST':
        p.nama = request.form.get('nama', '').upper()
        p.stok_lusin = int(request.form.get('lusin') or 0)
        p.stok_pcs = int(request.form.get('pcs') or 0)
        p.harga_grosir = int(request.form.get('harga_grosir') or 0)
        p.supplier = get_supplier_from_form(request.form)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit.html', p=p)

# --- ROUTES KASIR ---
@app.route('/kasir')
def kasir():
    produk = Produk.query.order_by(Produk.nama.asc()).all()
    return render_template('kasir.html', produk=produk)

@app.route('/tambah_penjualan', methods=['POST'])
def tambah_penjualan():
    nama = request.form.get('nama_barang')
    ls, pcs = int(request.form.get('jumlah_ls') or 0), int(request.form.get('jumlah_pcs') or 0)
    total_bayar = int(request.form.get('harga_jual') or 0)
    p = Produk.query.filter_by(nama=nama).first()
    if p:
        stok_total = (p.stok_lusin * 12) + p.stok_pcs
        jual_total = (ls * 12) + pcs
        if stok_total >= jual_total:
            sisa = stok_total - jual_total
            p.stok_lusin, p.stok_pcs = sisa // 12, sisa % 12
            db.session.add(Penjualan(nama_barang=nama, jumlah_ls=ls, jumlah_pcs=pcs, total_omzet=total_bayar))
            db.session.commit()
    return redirect(url_for('rincian_penjualan'))

# --- ROUTES RINCIAN PENJUALAN & EDIT PENJUALAN (FIX 404) ---
@app.route('/rincian_penjualan')
def rincian_penjualan():
    f = request.args.get('filter', 'semua')
    query = Penjualan.query
    if f != 'semua':
        start = datetime.now().replace(day=1) if f == 'bulan' else datetime.now() - timedelta(days=datetime.now().weekday())
        query = query.filter(Penjualan.tanggal_transaksi >= start)
    data = query.order_by(Penjualan.tanggal_transaksi.desc()).all()
    return render_template('rincian_penjualan.html', penjualan=data, total_omzet=sum(p.total_omzet for p in data), filter_aktif=f)

@app.route('/edit_penjualan/<int:id>', methods=['GET', 'POST'])
def edit_penjualan(id):
    p = Penjualan.query.get_or_404(id)
    
    if request.method == 'POST':
        # 1. Ambil input tanggal/waktu dari form
        tgl_input = request.form.get('tanggal_transaksi')
        if tgl_input:
            # Konversi string dari HTML 'YYYY-MM-DDTHH:MM' ke objek datetime Python
            p.tanggal_transaksi = datetime.strptime(tgl_input, '%Y-%m-%dT%H:%M')
        
        # 2. Ambil data jumlah barang
        p.jumlah_ls = int(request.form.get('jumlah_ls') or 0)
        p.jumlah_pcs = int(request.form.get('jumlah_pcs') or 0)
        
        # 3. Ambil data omset (sesuaikan dengan name="harga_jual" di edit_penjualan.html)
        p.total_omzet = int(request.form.get('harga_jual') or 0)
        
        # 4. Simpan ke database
        db.session.commit()
        
        flash("DATA TRANSAKSI BERHASIL DIPERBAHARUI!")
        return redirect(url_for('rincian_penjualan'))
    
    # Tampilkan halaman edit
    return render_template('edit_penjualan.html', p=p)
@app.route('/hapus_penjualan/<int:id>')
def hapus_penjualan(id):
    db.session.delete(Penjualan.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for('rincian_penjualan'))

# --- ROUTES PENGELUARAN ---
@app.route('/rincian_pengeluaran', methods=['GET', 'POST'])
def rincian_pengeluaran():
    if request.method == 'POST':
        nama = request.form.get('nama', '').upper()
        biaya = int(request.form.get('biaya') or 0)
        db.session.add(Pengeluaran(nama_pengeluaran=nama, jumlah_biaya=biaya))
        db.session.commit()
        return redirect(url_for('rincian_pengeluaran'))
    data = Pengeluaran.query.order_by(Pengeluaran.tanggal.desc()).all()
    return render_template('rincian_pengeluaran.html', pengeluaran=data, total_biaya=sum(e.jumlah_biaya for e in data))

@app.route('/hapus_pengeluaran/<int:id>')
def hapus_pengeluaran(id):
    db.session.delete(Pengeluaran.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for('rincian_pengeluaran'))

# --- LAPORAN ---
@app.route('/laporan')
def laporan():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    filter_supplier = request.args.get('supplier', '').strip()
    
    list_supplier = [s[0] for s in db.session.query(Produk.supplier).distinct().all() if s[0]]
    
    query = Produk.query
    if search:
        query = query.filter(Produk.nama.ilike(f'%{search}%'))
    if filter_supplier:
        query = query.filter(Produk.supplier == filter_supplier)
        
    pagination = query.order_by(Produk.id.desc()).paginate(page=page, per_page=50)
    
    # --- LOGIKA BARU: HITUNG TOTAL FISIK BARANG ---
    all_filtered = query.all()
    # 1. Totalkan semua ke satuan potong (pcs)
    total_potong_semua = sum((p.stok_lusin * 12) + p.stok_pcs for p in all_filtered)
    
    # 2. Konversi kembali ke Lusin dan Sisa Potong
    total_ls = total_potong_semua // 12
    total_pcs = total_potong_semua % 12
    
    # 3. Simpan dalam dictionary agar mudah dibaca di template
    total_fisik = {'lusin': total_ls, 'potong': total_pcs}
    
    return render_template('laporan.html', 
                           pagination=pagination, 
                           total_fisik=total_fisik, # Kirim variabel baru
                           search=search, 
                           all_suppliers=list_supplier, 
                           filter_supplier=filter_supplier)

@app.route('/laporan_pendapatan')
def laporan_pendapatan():
    f = request.args.get('filter', 'semua')
    q_jual, q_biaya = db.session.query(func.sum(Penjualan.total_omzet)), db.session.query(func.sum(Pengeluaran.jumlah_biaya))
    if f != 'semua':
        start = datetime.now().replace(day=1) if f == 'bulan' else datetime.now() - timedelta(days=datetime.now().weekday())
        q_jual, q_biaya = q_jual.filter(Penjualan.tanggal_transaksi >= start), q_biaya.filter(Pengeluaran.tanggal >= start)
    t_o, t_b = q_jual.scalar() or 0, q_biaya.scalar() or 0
    return render_template('laporan_pendapatan.html', t_o=t_o, t_b=t_b, laba=t_o-t_b, filter_aktif=f)
# --- TAMBAHKAN DI BAGIAN BAWAH app.py ---

# HAPUS VERSI LAMA, SISAKAN SATU SEPERTI INI SAJA:
@app.route('/import', methods=['POST'])
def import_excel():
    file = request.files.get('file')
    if not file:
        flash("TIDAK ADA FILE YANG DIPILIH!")
        return redirect(url_for('index'))
    
    try:
        df = pd.read_excel(file)
        # Validasi Kolom
        required_cols = ['nama', 'stok_lusin', 'stok_pcs', 'harga_grosir', 'supplier']
        
        if not all(col in df.columns for col in required_cols):
            flash(f"FORMAT SALAH! Rekomendasi kolom: {', '.join(required_cols)}")
            return redirect(url_for('index'))

        # Proses Simpan
        for _, r in df.iterrows():
            db.session.add(Produk(
                nama=str(r['nama']).upper(),
                stok_lusin=int(r['stok_lusin'] or 0),
                stok_pcs=int(r['stok_pcs'] or 0),
                harga_grosir=int(r['harga_grosir'] or 0),
                supplier=str(r['supplier'] or '-').upper()
            ))
        db.session.commit()
        flash("IMPORT BERHASIL DISINKRONKAN!")
    except Exception as e:
        flash(f"FILE TIDAK VALID: {str(e)}")
    
    return redirect(url_for('index'))
# --- DI APP.PY ---
# --- TAMBAHKAN DI app.py ---
@app.route('/hapus_masal', methods=['POST'])
def hapus_masal():
    ids = request.form.getlist('produk_ids') # Mengambil list ID dari checkbox
    if ids:
        Produk.query.filter(Produk.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f"BERHASIL MENGHAPUS {len(ids)} DATA PRODUK!")
    else:
        flash("TIDAK ADA DATA YANG DIPILIH!")
    return redirect(url_for('index'))
# --- ROUTE LAPORAN MINGGUAN (TAMBAHKAN KODE INI) ---
@app.route('/laporan_mingguan')
def laporan_mingguan():
    # 1. Tentukan Rentang Waktu (Minggu jam 00:00 s/d Sabtu jam 23:59)
    today = datetime.now()
    # Hari Minggu = 0, Senin = 1, ..., Sabtu = 6
    idx_hari = (today.weekday() + 1) % 7 
    start_minggu = (today - timedelta(days=idx_hari)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_sabtu = (start_minggu + timedelta(days=6)).replace(hour=23, minute=59, second=59)

    # 2. Ambil Data Penjualan dalam rentang tersebut
    penjualan_data = Penjualan.query.filter(
        Penjualan.tanggal_transaksi >= start_minggu,
        Penjualan.tanggal_transaksi <= end_sabtu
    ).all()

    # 3. Ambil Data Pengeluaran dalam rentang tersebut
    pengeluaran_data = Pengeluaran.query.filter(
        Pengeluaran.tanggal >= start_minggu,
        Pengeluaran.tanggal <= end_sabtu
    ).all()

    # 4. Olah Data Penjualan per Hari untuk Tabel
    hari_nama = ["MINGGU", "SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", "SABTU"]
    laporan_hari = []
    total_ls = 0
    total_pcs = 0
    total_rp = 0

    for i in range(7):
        tgl_target = start_minggu + timedelta(days=i)
        # Filter data per hari
        data_hari = [p for p in penjualan_data if p.tanggal_transaksi.date() == tgl_target.date()]
        
        sum_ls = sum(p.jumlah_ls for p in data_hari)
        sum_pcs = sum(p.jumlah_pcs for p in data_hari)
        sum_rp = sum(p.total_omzet for p in data_hari)
        
        laporan_hari.append({
            'hari': hari_nama[i],
            'ls': sum_ls,
            'pcs': sum_pcs,
            'rp': sum_rp
        })
        
        total_ls += sum_ls
        total_pcs += sum_pcs
        total_rp += sum_rp

    # 5. Hitung Total Pengeluaran & Omzet Bersih
    total_pengeluaran = sum(e.jumlah_biaya for e in pengeluaran_data)
    omzet_bersih = total_rp - total_pengeluaran

    return render_template('laporan_mingguan.html', 
                           laporan_hari=laporan_hari,
                           total_ls=total_ls,
                           total_pcs=total_pcs,
                           total_rp=total_rp,
                           pengeluaran=pengeluaran_data,
                           total_pengeluaran=total_pengeluaran,
                           omzet_bersih=omzet_bersih)
if __name__ == '__main__':
    app.run(debug=True)