// Copy-only host helper. IFileOperation reports completion before readback starts.
// Interface method order follows shobjidl_core.h; no move/delete method is called.
using System;
using System.Runtime.InteropServices;

namespace SilverStar {
    [ComImport, Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IShellItem { }

    [ComImport, Guid("947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IFileOperation {
        void Advise(IntPtr sink, out uint cookie);
        void Unadvise(uint cookie);
        void SetOperationFlags(uint flags);
        void SetProgressMessage([MarshalAs(UnmanagedType.LPWStr)] string message);
        void SetProgressDialog(IntPtr dialog);
        void SetProperties(IntPtr properties);
        void SetOwnerWindow(IntPtr window);
        void ApplyPropertiesToItem(IShellItem item);
        void ApplyPropertiesToItems(IntPtr items);
        void RenameItem(IShellItem item, [MarshalAs(UnmanagedType.LPWStr)] string name, IntPtr sink);
        void RenameItems(IntPtr items, [MarshalAs(UnmanagedType.LPWStr)] string name);
        void MoveItem(IShellItem item, IShellItem folder, [MarshalAs(UnmanagedType.LPWStr)] string name, IntPtr sink);
        void MoveItems(IntPtr items, IShellItem folder);
        void CopyItem(IShellItem item, IShellItem folder, [MarshalAs(UnmanagedType.LPWStr)] string name, IntPtr sink);
        void CopyItems(IntPtr items, IShellItem folder);
        void DeleteItem(IShellItem item, IntPtr sink);
        void DeleteItems(IntPtr items);
        void NewItem(IShellItem folder, uint attributes, [MarshalAs(UnmanagedType.LPWStr)] string name,
                     [MarshalAs(UnmanagedType.LPWStr)] string template, IntPtr sink);
        void PerformOperations();
        void GetAnyOperationsAborted([MarshalAs(UnmanagedType.Bool)] out bool aborted);
    }

    public static class MtpCopy {
        [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=false)]
        private static extern void SHCreateItemFromParsingName(string path, IntPtr context,
                                                               ref Guid id, out IShellItem item);
        [DllImport("shell32.dll", PreserveSig=false)]
        private static extern void SHGetIDListFromObject(
            [MarshalAs(UnmanagedType.IUnknown)] object value, out IntPtr pidl);
        [DllImport("shell32.dll", PreserveSig=false)]
        private static extern void SHCreateItemFromIDList(IntPtr pidl, ref Guid id, out IShellItem item);

        public static void Copy(string source, string folder, string name) {
            CopyShellItems(source, folder, name);
        }

        private static IShellItem Item_FromObject(object value) {
            Guid id = typeof(IShellItem).GUID;
            IShellItem item;
            if (value is string) {
                SHCreateItemFromParsingName((string)value, IntPtr.Zero, ref id, out item);
                return item;
            }
            IntPtr pidl = IntPtr.Zero;
            try {
                SHGetIDListFromObject(value, out pidl);
                SHCreateItemFromIDList(pidl, ref id, out item);
                return item;
            } finally {
                if (pidl != IntPtr.Zero) Marshal.FreeCoTaskMem(pidl);
            }
        }

        // Keep virtual items as Shell objects/PIDLs. Their automation Path is
        // not guaranteed to round-trip through a filesystem-style name parser.
        public static void CopyShellItems(object source, object folder, string name) {
            if (source == null || folder == null ||
                String.IsNullOrEmpty(name) || name.IndexOfAny(new char[] {'\\', '/', ':'}) >= 0)
                throw new ArgumentException("Explicit source, folder and basename required");
            IShellItem src = null, dst = null;
            IFileOperation operation = null;
            try {
                src = Item_FromObject(source);
                dst = Item_FromObject(folder);
                operation = (IFileOperation)Activator.CreateInstance(
                    Type.GetTypeFromCLSID(new Guid("3ad05575-8857-4850-9277-11b85bdb8e09")));
                // Silent, rename-on-collision (never replace), no error UI,
                // no security attribute copy, fail immediately on any error.
                operation.SetOperationFlags(0x00100C0C);
                operation.CopyItem(src, dst, name, IntPtr.Zero);
                operation.PerformOperations();
                bool aborted;
                operation.GetAnyOperationsAborted(out aborted);
                if (aborted) throw new OperationCanceledException("Windows copy was aborted");
            } finally {
                if (operation != null) Marshal.FinalReleaseComObject(operation);
                if (dst != null) Marshal.FinalReleaseComObject(dst);
                if (src != null) Marshal.FinalReleaseComObject(src);
            }
        }
    }
}
