import { KeyRound, Save, UserRound } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { api } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import { useNavigate } from "react-router-dom";

export default function Profile() {
  const { user, refreshProfile, clearAuth } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState(user?.full_name || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  async function saveProfile(event) {
    event.preventDefault();
    setSavingProfile(true);
    try {
      await api.patch("/users/me", { full_name: name });
      await refreshProfile();
      toast.success("Profile updated.");
    } catch (error) {
      toast.error(error.userMessage || "Could not update your profile.");
    } finally {
      setSavingProfile(false);
    }
  }

  async function changePassword(event) {
    event.preventDefault();
    setSavingPassword(true);
    try {
      const { data } = await api.post("/users/me/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      toast.success(data.message || "Password updated. Please sign in again.");
      setCurrentPassword("");
      setNewPassword("");
      clearAuth();
      navigate("/login", { replace: true });
    } catch (error) {
      toast.error(error.userMessage || "Could not change your password.");
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <p className="text-sm font-semibold text-indigo-600">Account</p>
      <h1 className="mt-1 text-3xl font-bold text-slate-900">Profile settings</h1>
      <div className="mt-7 grid gap-5">
        <form className="card" onSubmit={saveProfile}>
          <div className="flex items-center gap-2">
            <UserRound className="text-indigo-600" size={19} />
            <h2 className="font-semibold text-slate-900">Profile information</h2>
          </div>
          <label className="mt-5 block text-sm font-medium text-slate-700">
            Full name
            <input className="field mt-2" value={name} minLength={2} maxLength={255} required onChange={(event) => setName(event.target.value)} />
          </label>
          <p className="mt-3 text-sm text-slate-500">Email: {user?.email}</p>
          <button className="button-primary mt-5" type="submit" disabled={savingProfile}>
            <Save size={16} /> Save changes
          </button>
        </form>

        <form className="card" onSubmit={changePassword}>
          <div className="flex items-center gap-2">
            <KeyRound className="text-indigo-600" size={19} />
            <h2 className="font-semibold text-slate-900">Change password</h2>
          </div>
          <label className="mt-5 block text-sm font-medium text-slate-700">
            Current password
            <input className="field mt-2" type="password" autoComplete="current-password" value={currentPassword} required onChange={(event) => setCurrentPassword(event.target.value)} />
          </label>
          <label className="mt-4 block text-sm font-medium text-slate-700">
            New password
            <input className="field mt-2" type="password" autoComplete="new-password" minLength={8} maxLength={128} value={newPassword} required onChange={(event) => setNewPassword(event.target.value)} />
            <span className="mt-1 block text-xs font-normal text-slate-400">At least 8 characters. Other active refresh sessions will be revoked.</span>
          </label>
          <button className="button-primary mt-5" type="submit" disabled={savingPassword}>
            <KeyRound size={16} /> Update password
          </button>
        </form>
      </div>
    </main>
  );
}
