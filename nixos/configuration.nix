# Edit this configuration file to define what should be installed on
# your system. Help is available in the configuration.nix(5) man page, on
# https://search.nixos.org/options and in the NixOS manual (`nixos-help`).

{ config, pkgs, ... }:

{
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
    ];

  # Use the systemd-boot EFI boot loader.
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  networking.hostName = "blackbox"; # Define your hostname.
  # networking.wireless.enable = true;  # Enables wireless support via wpa_supplicant.

  # Configure network proxy if necessary
  # networking.proxy.default = "http://user:password@proxy:port/";
  # networking.proxy.noProxy = "127.0.0.1,localhost,internal.domain";

  # Enable networking
  networking.networkmanager.enable = true;

  # Set your time zone.
  time.timeZone = "America/Guadeloupe";

  # Select internationalisation properties.
  i18n.defaultLocale = "en_US.UTF-8";

  # Configure keymap in X11
  services.xserver.xkb = {
    layout = "fr";
    variant = "azerty";
  };

  # Configure console keymap
  console.keyMap = "fr";

  users.groups.k3s-admins = { };

  # Define a user account. Don't forget to set a password with ‘passwd’.
  users.users."boli" = {
    isNormalUser = true;
    description = "boli";
    extraGroups = [ "networkmanager" "wheel" "k3s-admins" ];
    packages = with pkgs; [];
    openssh.authorizedKeys.keys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPRPrtAUlgjacsSDKV6/YWQ9wGnCHwF/OxYD8hs5VG3f"
    ];
  };

  # Allow unfree packages
  nixpkgs.config.allowUnfree = true;

  # List packages installed in system profile.
  # You can use https://search.nixos.org/ to find more packages (and options).
  environment.systemPackages = with pkgs; [
    git
    vim
    wget
    htop
    smartmontools
  ];

  environment.shellAliases.k = "k3s kubectl";

  # Some programs need SUID wrappers, can be configured further or are
  # started in user sessions.
  # programs.mtr.enable = true;
  # programs.gnupg.agent = {
  #   enable = true;
  #   enableSSHSupport = true;
  # };

  # List services that you want to enable:

  # Enable the OpenSSH daemon.
  services.openssh.enable = true;

  services.k3s = {
    enable = true;
    role = "server";
    package = pkgs.k3s_1_36;
    disable = [ "servicelb" ];
    extraFlags = [
      "--write-kubeconfig-mode=0640"
      "--write-kubeconfig-group=k3s-admins"
    ];
  };

  # Open ports in the firewall.
  # networking.firewall.allowedTCPPorts = [ ... ];
  # networking.firewall.allowedUDPPorts = [ ... ];
  # Or disable the firewall altogether.
  networking.firewall.enable = false;

  networking = {
     useDHCP = false;
     dhcpcd.enable = false;
     interfaces.enp2s0 = {
       ipv4.addresses = [{
         address = "192.168.1.200";
         prefixLength = 24;
       }];
     };
     defaultGateway = {
       address = "192.168.1.1";
       interface = "enp2s0";
     };
     nameservers = [ "1.1.1.1" "9.9.9.9" ];
  };

  fileSystems."/mnt/bigdata" = {
    device = "192.168.1.201:/volume1/media";
    fsType = "nfs";
    options = [ "nofail" "x-systemd.automount" ];
  };

  systemd.tmpfiles.rules = [
    "d /mnt/downloads 0775 1024 100 -"
    "d /mnt/downloads/radarr 0775 1024 100 -"
    "d /mnt/downloads/sonarr 0775 1024 100 -"
  ];

  # Copy the NixOS configuration file and link it from the resulting system
  # (/run/current-system/configuration.nix). This is useful in case you
  # accidentally delete configuration.nix.
  # system.copySystemConfiguration = true;

  # This option defines the first version of NixOS you have installed on this particular machine,
  # and is used to maintain compatibility with application data (e.g. databases) created on older NixOS versions.
  #
  # Most users should NEVER change this value after the initial install, for any reason,
  # even if you've upgraded your system to a new NixOS release.
  #
  # This value does NOT affect the Nixpkgs version your packages and OS are pulled from,
  # so changing it will NOT upgrade your system - see https://nixos.org/manual/nixos/stable/#sec-upgrading for how
  # to actually do that.
  #
  # This value being lower than the current NixOS release does NOT mean your system is
  # out of date, out of support, or vulnerable.
  #
  # Do NOT change this value unless you have manually inspected all the changes it would make to your configuration,
  # and migrated your data accordingly.
  #
  # For more information, see `man configuration.nix` or https://nixos.org/manual/nixos/stable/options#opt-system.stateVersion .
  system.stateVersion = "26.05"; # Did you read the comment?

}
