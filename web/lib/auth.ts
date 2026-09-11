import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

const ALLOWED_ADMIN_EMAIL = process.env.ALLOWED_ADMIN_EMAIL;

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [Google],
  callbacks: {
    // Single-user gate (see plan: Auth & Sharing) — only the owner's
    // Google account may sign in.
    signIn({ profile }) {
      return profile?.email === ALLOWED_ADMIN_EMAIL;
    },
  },
  pages: {
    signIn: "/login",
  },
});
