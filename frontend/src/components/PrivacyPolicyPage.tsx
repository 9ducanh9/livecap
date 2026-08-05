import { ArrowLeft, ShieldCheck } from 'lucide-react';

const EFFECTIVE_DATE = 'August 5, 2026';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t border-[#dce5f2] py-8 first:border-t-0 first:pt-0">
      <h2 className="font-instrument text-2xl font-bold tracking-[-0.03em] text-[#102247]">{title}</h2>
      <div className="space-y-3 text-sm leading-7 text-[#435572]">{children}</div>
    </section>
  );
}

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-[#f7f8fc] text-[#102247]">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8 lg:px-10">
        <a href="/" className="flex items-center gap-2.5 font-instrument text-xl font-bold tracking-[-0.08em] text-[#102247]" aria-label="LiveCap home">
          <img src="/LiveCap.svg" alt="" className="h-10 w-10 rounded-xl" />
          LIVECAP
        </a>
        <a href="/" className="flex items-center gap-2 text-sm font-semibold text-[#52647f] transition-colors hover:text-[#102247]">
          <ArrowLeft className="h-4 w-4" /> Back to home
        </a>
      </header>

      <main className="mx-auto max-w-3xl px-5 pb-24 pt-6 sm:px-8 lg:px-10">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[#9ce5d7] bg-white/70 px-3 py-1.5 text-xs font-bold tracking-wide text-[#087b6c] shadow-sm">
          <ShieldCheck className="h-3.5 w-3.5" /> PRIVACY POLICY
        </div>
        <h1 className="font-instrument text-4xl font-bold tracking-[-0.05em] text-[#102247] sm:text-5xl">
          Your privacy, plainly explained.
        </h1>
        <p className="mt-3 text-sm font-medium text-[#71819a]">Effective {EFFECTIVE_DATE}</p>
        <p className="mt-6 text-base leading-8 text-[#435572]">
          LiveCap ("we," "our," "LiveCap") provides real-time bilingual meeting
          captions and translation. This page explains what information we
          collect, why, and the choices you have. It applies to
          livecap.logantai.com and the LiveCap caption workspace.
        </p>

        <div className="mt-10 rounded-2xl border border-[#9ce5d7] bg-white/70 p-6 shadow-sm">
          <p className="text-sm font-bold text-[#087b6c]">The short version</p>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-[#435572]">
            <li>• We never sell your data or share it with third parties for their own marketing or advertising.</li>
            <li>• Signing in with Google only requests your email address, name, and profile picture — nothing else.</li>
            <li>• Your raw microphone audio is never stored — only finalized text captions, and only if you keep a transcript.</li>
            <li>• You can delete your account and your data at any time.</li>
          </ul>
        </div>

        <Section title="Information we collect">
          <p><strong>Account information.</strong> When you create an account, we collect your email address and, if you sign in with Google, your name and profile picture. If you sign in with email and password instead, we only collect the email address and a securely hashed password (we never see or store your password in plain text — that's handled entirely by Amazon Cognito, our authentication provider).</p>
          <p><strong>Session and caption data.</strong> While a live session is running, your microphone audio is streamed to our transcription service in real time and immediately discarded — <strong>we do not record or store raw audio</strong>. Only the finalized text captions (and their translations) are kept, and only for the duration described in "How long we keep data" below.</p>
          <p><strong>Usage data.</strong> We track how many sessions and minutes your account has used each month, to enforce plan limits (Free/Pro/Business) and, if you subscribe, to bill correctly.</p>
          <p><strong>Billing information.</strong> If you subscribe to a paid plan, payment is handled entirely by Stripe. We never see or store your card number — we only receive your subscription status and tier from Stripe.</p>
          <p><strong>Technical information.</strong> Like most web apps, our infrastructure logs standard operational data (timestamps, error rates, request counts) for reliability and security monitoring. These logs are not used to build advertising profiles.</p>
        </Section>

        <Section title="Signing in with Google">
          <p>When you choose "Continue with Google," we request only three basic OpenID Connect scopes:</p>
          <ul className="ml-5 list-disc space-y-1">
            <li><code className="rounded bg-[#eef2f8] px-1.5 py-0.5 text-xs">openid</code> — to verify your identity</li>
            <li><code className="rounded bg-[#eef2f8] px-1.5 py-0.5 text-xs">email</code> — your email address</li>
            <li><code className="rounded bg-[#eef2f8] px-1.5 py-0.5 text-xs">profile</code> — your name and profile picture</li>
          </ul>
          <p>We do not request access to your Gmail, Google Drive, Contacts, Calendar, or any other Google service or data. We cannot read, send, or modify anything in your Google account beyond this basic sign-in information.</p>
        </Section>

        <Section title="We do not sell or share your data">
          <p>We do not sell your personal information, and we do not share it with third parties for their own marketing, advertising, or any other independent purpose — ever.</p>
          <p>To operate LiveCap, we do rely on infrastructure and payment providers who process data strictly on our behalf, under their own security and confidentiality commitments, and never for their own purposes:</p>
          <ul className="ml-5 list-disc space-y-1">
            <li><strong>Amazon Web Services</strong> — hosts our application and processes audio for transcription (Amazon Transcribe), translation (Amazon Translate), optional AI meeting notes (Amazon Bedrock), and stores account and caption data (DynamoDB, S3), all within our own private AWS account.</li>
            <li><strong>Amazon Cognito</strong> — manages sign-in and password security.</li>
            <li><strong>Stripe</strong> — processes subscription payments; LiveCap never receives your full card number.</li>
          </ul>
          <p>None of these providers are permitted to use your data for their own advertising or resell it.</p>
        </Section>

        <Section title="How long we keep data">
          <ul className="ml-5 list-disc space-y-1">
            <li><strong>Raw audio:</strong> never stored — processed in memory during transcription only.</li>
            <li><strong>Finalized transcripts:</strong> kept for 14 days, then automatically and permanently deleted.</li>
            <li><strong>Monthly usage records:</strong> kept for 90 days, then automatically deleted.</li>
            <li><strong>Account information:</strong> kept until you delete your account, at which point it is permanently removed.</li>
          </ul>
        </Section>

        <Section title="Your choices and rights">
          <p>You can download a finalized transcript at any time during the retention window, and you can request deletion of your account and all associated data by contacting us. Deleting your account removes your Google/email sign-in record and your stored usage and profile data from our systems.</p>
        </Section>

        <Section title="Security">
          <p>Your data is encrypted in transit (HTTPS/WSS) and at rest. Stored captions and account data live in private, access-controlled cloud storage that is never publicly reachable. Our infrastructure is protected by a web application firewall and network isolation between the public internet and the systems that process your data.</p>
        </Section>

        <Section title="Children's privacy">
          <p>LiveCap is not directed at children under 13, and we do not knowingly collect personal information from children under 13.</p>
        </Section>

        <Section title="Changes to this policy">
          <p>If we make material changes to this policy, we will update the effective date above and, where appropriate, notify signed-in users.</p>
        </Section>

        <Section title="Contact us">
          <p>Questions about this policy or your data? Reach us at <a className="font-semibold text-[#0a9c88] underline" href="mailto:privacy@livecap.logantai.com">privacy@livecap.logantai.com</a>.</p>
        </Section>
      </main>
    </div>
  );
}
