/** Captured input changes, independent from a form's explicit dirty/busy guard. */
export class CapturedModalChanges {
  private revision = 0;
  private confirmed = 0;
  capture(): void { this.revision++; }
  checkpoint(): number { return this.revision; }
  reset(checkpoint = this.revision): void {
    this.confirmed = Math.max(this.confirmed, Math.min(checkpoint, this.revision));
  }
  get dirty(): boolean { return this.revision > this.confirmed; }
}

export interface ModalChangeReceipt {
  checkpoint(): number;
  reset(checkpoint?: number): void;
}

/** A rejected or uncertain command leaves its draft guard intact. */
export async function afterConfirmedModalChange<T>(changes: ModalChangeReceipt | null, work: () => Promise<T>): Promise<T> {
  const checkpoint = changes?.checkpoint();
  const result = await work();
  if (checkpoint !== undefined) changes?.reset(checkpoint);
  return result;
}
