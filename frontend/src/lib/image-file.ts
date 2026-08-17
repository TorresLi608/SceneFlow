/**
 * Reading an image the user picked into the `data:` URL the API expects.
 *
 * Every image the frontend sends — chat attachments, image-to-image references, covers,
 * character sheets — travels as a data URL rather than multipart, so the size and type
 * checks that mirror `artifact_service.decode_image_data_url` live here once.
 */

/** Mirrors the ceiling `artifact_service.decode_image_data_url` enforces server-side. */
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];

export type ImageReadError = "unsupported" | "too-large" | "unreadable";

export type ImageReadResult = { ok: true; dataUrl: string } | { ok: false; reason: ImageReadError };

function readDataURL(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

/** Never throws: callers get a reason they can turn into a translated message. */
export async function readImageFile(file: File): Promise<ImageReadResult> {
  if (!IMAGE_TYPES.includes(file.type)) {
    return { ok: false, reason: "unsupported" };
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return { ok: false, reason: "too-large" };
  }
  try {
    return { ok: true, dataUrl: await readDataURL(file) };
  } catch {
    return { ok: false, reason: "unreadable" };
  }
}
