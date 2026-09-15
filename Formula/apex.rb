# typed: false
# frozen_string_literal: true

class Apex < Formula
  desc "Adaptive Tournament Multi-Engine Compression Tool & Next-Gen Container"
  homepage "https://qxmcu.github.io/apex/"
  version "1.2.0"
  license "GPL-3.0-or-later"

  on_macos do
    url "https://github.com/qxmcu/apex/releases/download/v1.2.0/apex-v1.2.0-darwin-x86_64.tar.gz"
    sha256 "af9ac0cc8ea5b07ce086135fc342d219086ef142b7637fa24091742627d76b06"
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/qxmcu/apex/releases/download/v1.2.0/apex-v1.2.0-linux-x86_64.tar.gz"
      sha256 "4c8d2036c05160893086300a7faae95fa809e530fe71946eb253818e692a8fa2"
    end
  end

  def install
    bin.install "apex"

    # Generate and install shell completions
    generate_completions_from_executable(bin/"apex", "completions")
  end

  test do
    assert_match "apex 1.2.0", shell_output("#{bin}/apex --version")
  end
end
