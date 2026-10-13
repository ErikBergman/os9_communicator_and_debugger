/* WARNING: Unknown calling convention -- yet parameter storage is locked */

short CloseFreddiFile(undefined *file)

{
  short sVar1;
  undefined4 *puVar2;
  int iVar3;
  undefined4 auStack_160 [4];
  short sStack_150;
  undefined1 *puStack_14e;
  undefined2 uStack_14a;
  undefined2 uStack_148;
  undefined1 uStack_146;
  undefined2 uStack_144;
  undefined4 uStack_130;
  undefined2 uStack_12c;
  undefined4 uStack_126;
  short sStack_120;
  undefined1 auStack_e0 [208];

  puVar2 = auStack_160;
  iVar3 = 0x10;
  do {
    *puVar2 = 0;
    puVar2 = puVar2 + 1;
    iVar3 = iVar3 + -1;
  } while (iVar3 != 0);
  puStack_14e = auStack_e0;
  uStack_148 = *(undefined2 *)(file + 6);
  sVar1 = PBGetFCBInfoSync((undefined *)auStack_160);
  if (sVar1 != 0) {
    return sStack_150;
  }
  iVar3 = 0;
  puStack_14e = (undefined1 *)0x0;
  uStack_14a = uStack_12c;
  if ((*file & 1) != 0) {
    uStack_144 = 0;
    sVar1 = PBHGetVInfoSync((undefined *)auStack_160);
    if (sVar1 != 0) {
      return sStack_150;
    }
    if (sStack_120 == 0x4244) {
      iVar3 = 2;
    }
    else {
      if (sStack_120 != -0x2d29) goto LAB_10005bf0;
      iVar3 = 1;
    }
    puStack_14e = auStack_e0;
    uStack_130 = uStack_126;
    uStack_146 = 0;
  }
LAB_10005bf0:
  uStack_14a = uStack_12c;
  uStack_148 = *(undefined2 *)(file + 6);
  sVar1 = PBCloseSync((undefined *)auStack_160);
  if (sVar1 == 0) {
    if (iVar3 != 0) {
      if (iVar3 == 1) {
        PBDeleteSync((undefined *)auStack_160);
      }
      else {
        PBHDeleteSync((undefined *)auStack_160);
      }
    }
    puStack_14e = (undefined1 *)0x0;
    PBFlushVolSync((undefined *)auStack_160);
  }
  return sStack_150;
}
