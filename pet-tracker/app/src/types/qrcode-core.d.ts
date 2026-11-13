// The core encoder of the `qrcode` package (no types are published for it).
declare module 'qrcode/lib/core/qrcode' {
  const QRCodeCore: {
    create(text: string, options?: { errorCorrectionLevel?: 'L' | 'M' | 'Q' | 'H' }): {
      modules: { size: number; data: Uint8Array | boolean[] };
    };
  };
  export default QRCodeCore;
}
