import { open, type FileHandle } from 'node:fs/promises';
import { setTimeout as delay } from 'node:timers/promises';

// Windows reports EBUSY/EPERM while another process (antivirus, indexer, backup)
// briefly holds the file. These clear on their own within moments.
const TRANSIENT = new Set(['EBUSY', 'EPERM', 'EAGAIN']);
const RETRY_DELAYS_MS = [20, 50, 100, 200, 400, 800];

type AuditFile = Pick<FileHandle, 'write' | 'close'>;
export interface AuditLogOptions {
  open?: (file: string, flags: string) => Promise<AuditFile>;
  retryDelaysMs?: readonly number[];
}

/** Append-only run audit file.
 *
 * One handle stays open for the run instead of open/append/close per event,
 * so a streamed answer no longer reopens the file for every token. Records are
 * written in call order, and records that arrive during a write go out together
 * in the next one. A write that still fails after the transient retries rejects
 * its callers, but the bytes stay queued and go out with the next write or with
 * close(); one failure never blocks later records.
 */
export class AuditLog {
  private handle?: AuditFile;
  private pending: Buffer[] = [];
  private tail: Promise<void> = Promise.resolve();
  private next?: Promise<void>;
  private closed = false;
  private readonly openFile: NonNullable<AuditLogOptions['open']>;
  private readonly retryDelaysMs: readonly number[];

  constructor(readonly file: string, options: AuditLogOptions = {}) {
    this.openFile = options.open ?? open;
    this.retryDelaysMs = options.retryDelaysMs ?? RETRY_DELAYS_MS;
  }

  /** Settles once this record and everything queued before it is on disk. */
  append(line: string): Promise<void> {
    this.pending.push(Buffer.from(line, 'utf8'));
    return this.flush();
  }

  flush(): Promise<void> {
    // Everything queued while a write is in flight shares the single write after it.
    if (!this.next) {
      const attempt = this.tail.then(() => {
        this.next = undefined;
        return this.drain();
      });
      this.next = attempt;
      // The chain itself never rejects; callers receive the outcome of their own write.
      this.tail = attempt.catch(() => {});
    }
    return this.next;
  }

  /** Writes what is still queued and releases the handle. A later record opens the file just for itself. */
  close(): Promise<void> {
    this.closed = true;
    return this.flush();
  }

  private async drain(): Promise<void> {
    if (this.pending.length) {
      const data = Buffer.concat(this.pending);
      this.pending = [];
      let written = 0;
      try {
        for (let attempt = 0; ; attempt++) {
          try {
            this.handle ??= await this.openFile(this.file, 'a');
            while (written < data.length) written += (await this.handle.write(data, written, data.length - written, null)).bytesWritten;
            break;
          } catch (error) {
            // Reopen on the next attempt. The write error is the one to report;
            // a close error on that same handle adds nothing.
            const failed = this.handle;
            this.handle = undefined;
            await failed?.close().catch(() => {});
            const code = (error as NodeJS.ErrnoException).code;
            if (!code || !TRANSIENT.has(code) || attempt >= this.retryDelaysMs.length) throw error;
            await delay(this.retryDelaysMs[attempt]);
          }
        }
      } catch (error) {
        // Keep only the unwritten remainder, ahead of anything queued meanwhile.
        this.pending.unshift(data.subarray(written));
        throw error;
      }
    }
    if (this.closed && this.handle) {
      const handle = this.handle;
      this.handle = undefined;
      await handle.close();
    }
  }
}
