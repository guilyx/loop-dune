import Link from "next/link";

export default function NotFound() {
  return (
    <div className="card" style={{ maxWidth: 520 }}>
      <h1 style={{ fontSize: 22 }}>Not found</h1>
      <p className="lede">That market or page does not exist.</p>
      <p>
        <Link href="/">Back to the overview</Link>
      </p>
    </div>
  );
}
