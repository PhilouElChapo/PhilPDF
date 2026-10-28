/* Encodeur JBIG2 sans perte (region generique, gabarit 0, prediction typique TPGDON, codeur arithmetique MQ),
 * au format attendu par le filtre /JBIG2Decode des PDF : segment d'information de page + region generique.
 * Norme ITU-T T.88, annexe E (codeur MQ) et 6.2 (region generique). Pas de symboles : aucune lettre ne peut etre
 * remplacee par une autre (le defaut des JBIG2 « avec perte »).
 *
 * Entree : bitmap 1 bit par pixel, lignes de « pas » octets, 1 = noir.
 * Sortie : octets du flux ; renvoie la longueur, ou -1 si le tampon est trop petit.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

static const uint32_t QE[47] = {
    0x5601, 0x3401, 0x1801, 0x0AC1, 0x0521, 0x0221, 0x5601, 0x5401, 0x4801, 0x3801, 0x3001, 0x2401,
    0x1C01, 0x1601, 0x5601, 0x5401, 0x5101, 0x4801, 0x3801, 0x3401, 0x3001, 0x2801, 0x2401, 0x2201,
    0x1C01, 0x1801, 0x1601, 0x1401, 0x1201, 0x1101, 0x0AC1, 0x09C1, 0x08A1, 0x0521, 0x0441, 0x02A1,
    0x0221, 0x0141, 0x0111, 0x0085, 0x0049, 0x0025, 0x0015, 0x0009, 0x0005, 0x0001, 0x5601};
static const uint8_t NMPS[47] = {1, 2, 3, 4, 5, 38, 7, 8, 9, 10, 11, 12, 13, 29, 15, 16, 17, 18, 19, 20, 21, 22,
                                 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42,
                                 43, 44, 45, 45, 46};
static const uint8_t NLPS[47] = {1, 6, 9, 12, 29, 33, 6, 14, 14, 14, 17, 18, 20, 21, 14, 14, 15, 16, 17, 18, 19,
                                 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38,
                                 39, 40, 41, 42, 43, 46};
static const uint8_t SWITCH[47] = {1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

typedef struct {
    uint32_t a, c;
    int ct;
    int b;            /* octet courant (-1 : aucun encore) */
    uint8_t *out;
    long n, cap;
    int trop;
    uint8_t *i, *mps; /* etat de chaque contexte */
} Mq;

static void sortir(Mq *m, int octet) {
    if (m->b >= 0) {
        if (m->n >= m->cap) { m->trop = 1; } else { m->out[m->n] = (uint8_t)m->b; }
        m->n++;
    }
    m->b = octet;
}

static void byteout(Mq *m) {
    if (m->b == 0xFF) {
        sortir(m, (int)(m->c >> 20));
        m->c &= 0xFFFFF;
        m->ct = 7;
    } else if (m->c < 0x8000000) {
        sortir(m, (int)(m->c >> 19));
        m->c &= 0x7FFFF;
        m->ct = 8;
    } else {
        if (m->b >= 0) m->b++;
        if (m->b == 0xFF) {
            m->c &= 0x7FFFFFF;
            sortir(m, (int)(m->c >> 20));
            m->c &= 0xFFFFF;
            m->ct = 7;
        } else {
            sortir(m, (int)(m->c >> 19));
            m->c &= 0x7FFFF;
            m->ct = 8;
        }
    }
}

static void renorme(Mq *m) {
    do {
        m->a <<= 1;
        m->c <<= 1;
        m->ct--;
        if (m->ct == 0) byteout(m);
    } while ((m->a & 0x8000) == 0);
}

static void coder(Mq *m, uint32_t cx, int d) {
    int i = m->i[cx];
    uint32_t qe = QE[i];
    if (d == m->mps[cx]) {
        m->a -= qe;
        if ((m->a & 0x8000) == 0) {
            if (m->a < qe) m->a = qe; else m->c += qe;
            m->i[cx] = NMPS[i];
            renorme(m);
        } else {
            m->c += qe;
        }
    } else {
        m->a -= qe;
        if (m->a < qe) m->c += qe; else m->a = qe;
        if (SWITCH[i]) m->mps[cx] = 1 - m->mps[cx];
        m->i[cx] = NLPS[i];
        renorme(m);
    }
}

static void vider(Mq *m) {
    uint32_t t = m->c + m->a;
    m->c |= 0xFFFF;
    if (m->c >= t) m->c -= 0x8000;
    m->c <<= m->ct;
    byteout(m);
    m->c <<= m->ct;
    byteout(m);
    sortir(m, m->b);         /* l'octet courant */
    m->b = -1;
    if (m->n == 0 || m->out[m->n - 1] != 0xFF) sortir(m, 0xFF), sortir(m, -1);
    sortir(m, 0xAC);
    sortir(m, -1);
}

static void be32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}

static inline int px(const uint8_t *img, int w, int h, int pas, int x, int y) {
    if (x < 0 || y < 0 || x >= w || y >= h) return 0;
    return (img[(long)y * pas + (x >> 3)] >> (7 - (x & 7))) & 1;
}

EXPORT long philpdf_jbig2(const uint8_t *img, int w, int h, int pas, uint8_t *out, long cap) {
    if (cap < 80) return -1;
    /* segment 0 : information de page (type 48), 19 octets */
    uint8_t *p = out;
    be32(p, 0); p[4] = 48; p[5] = 0; p[6] = 1; be32(p + 7, 19); p += 11;
    be32(p, (uint32_t)w); be32(p + 4, (uint32_t)h); be32(p + 8, 0); be32(p + 12, 0);
    p[16] = 1;               /* page sans perte */
    p[17] = 0; p[18] = 0;    /* pas de bandes */
    p += 19;
    /* segment 1 : region generique immediate sans perte (type 38) */
    uint8_t *ent = p;
    be32(p, 1); p[4] = 38; p[5] = 0; p[6] = 1; /* longueur ecrite a la fin */ p += 11;
    be32(p, (uint32_t)w); be32(p + 4, (uint32_t)h); be32(p + 8, 0); be32(p + 12, 0); p[16] = 0; p += 17;
    p[0] = 0x08;             /* MMR 0, gabarit 0, TPGDON */
    p[1] = 3; p[2] = (uint8_t)-1; p[3] = (uint8_t)-3; p[4] = (uint8_t)-1;
    p[5] = 2; p[6] = (uint8_t)-2; p[7] = (uint8_t)-2; p[8] = (uint8_t)-2;
    p += 9;
    Mq m;
    memset(&m, 0, sizeof m);
    m.a = 0x8000; m.c = 0; m.ct = 12; m.b = -1;
    m.out = p; m.cap = cap - (p - out);
    m.i = (uint8_t *)calloc(65536, 1);
    m.mps = (uint8_t *)calloc(65536, 1);
    if (!m.i || !m.mps) { free(m.i); free(m.mps); return -1; }
    int ltp = 0;
    for (int y = 0; y < h; y++) {
        int pareil;
        if (y == 0) {
            pareil = 1;
            for (int k = 0; k < pas && pareil; k++) if (img[k]) pareil = 0;
        } else {
            pareil = memcmp(img + (long)y * pas, img + (long)(y - 1) * pas, pas) == 0;
        }
        coder(&m, 0x9B25, ltp ^ pareil);
        ltp = pareil;
        if (pareil) continue;
        for (int x = 0; x < w; x++) {
            uint32_t cx = 0;
            cx |= px(img, w, h, pas, x - 1, y) << 0;
            cx |= px(img, w, h, pas, x - 2, y) << 1;
            cx |= px(img, w, h, pas, x - 3, y) << 2;
            cx |= px(img, w, h, pas, x - 4, y) << 3;
            cx |= px(img, w, h, pas, x + 3, y - 1) << 4;
            cx |= px(img, w, h, pas, x + 2, y - 1) << 5;
            cx |= px(img, w, h, pas, x + 1, y - 1) << 6;
            cx |= px(img, w, h, pas, x + 0, y - 1) << 7;
            cx |= px(img, w, h, pas, x - 1, y - 1) << 8;
            cx |= px(img, w, h, pas, x - 2, y - 1) << 9;
            cx |= px(img, w, h, pas, x - 3, y - 1) << 10;
            cx |= px(img, w, h, pas, x + 2, y - 2) << 11;
            cx |= px(img, w, h, pas, x + 1, y - 2) << 12;
            cx |= px(img, w, h, pas, x + 0, y - 2) << 13;
            cx |= px(img, w, h, pas, x - 1, y - 2) << 14;
            cx |= px(img, w, h, pas, x - 2, y - 2) << 15;
            coder(&m, cx, px(img, w, h, pas, x, y));
            if (m.trop) break;
        }
        if (m.trop) break;
    }
    vider(&m);
    free(m.i);
    free(m.mps);
    if (m.trop) return -1;
    long donnees = (p - ent - 11) + m.n;
    be32(ent + 7, (uint32_t)donnees);
    return (long)(p - out) + m.n;
}
